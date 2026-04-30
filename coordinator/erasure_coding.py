import numpy as np

class GFMatrix:
    """A matrix class where all arithmetic is over GF(2^8)."""
    def __init__(self, rows, cols, rs_instance):
        self.rows = rows
        self.cols = cols
        self.rs = rs_instance
        self.data = [[0] * cols for _ in range(rows)]

    def __getitem__(self, idx):
        return self.data[idx]
    
    def __setitem__(self, idx, val):
        self.data[idx] = val

    def multiply(self, other):
        if self.cols != other.rows:
            raise ValueError("Matrix dimensions do not match for multiplication")
        result = GFMatrix(self.rows, other.cols, self.rs)
        for i in range(self.rows):
            for j in range(other.cols):
                val = 0
                for k in range(self.cols):
                    # GF Addition is XOR
                    val ^= self.rs.gf_mul(self.data[i][k], other.data[k][j])
                result.data[i][j] = val
        return result

    def invert(self):
        """Invert a square matrix using Gaussian elimination over GF(2^8)."""
        if self.rows != self.cols:
            raise ValueError("Matrix must be square to invert")
        
        n = self.rows
        # Create augmented matrix [A | I]
        aug = GFMatrix(n, n * 2, self.rs)
        for i in range(n):
            for j in range(n):
                aug.data[i][j] = self.data[i][j]
            aug.data[i][n + i] = 1 # Identity matrix on the right

        # Gaussian Elimination
        for p in range(n):
            # Find pivot
            if aug.data[p][p] == 0:
                for r in range(p + 1, n):
                    if aug.data[r][p] != 0:
                        aug.data[p], aug.data[r] = aug.data[r], aug.data[p]
                        break
                if aug.data[p][p] == 0:
                    raise ValueError("Matrix is singular (uninvertible)")
            
            # Scale pivot row to 1
            inv_pivot = self.rs.gf_div(1, aug.data[p][p])
            for c in range(n * 2):
                aug.data[p][c] = self.rs.gf_mul(aug.data[p][c], inv_pivot)

            # Eliminate other rows
            for r in range(n):
                if r != p and aug.data[r][p] != 0:
                    factor = aug.data[r][p]
                    for c in range(n * 2):
                        aug.data[r][c] ^= self.rs.gf_mul(factor, aug.data[p][c])

        # Extract inverted matrix from the right side
        inv = GFMatrix(n, n, self.rs)
        for i in range(n):
            for j in range(n):
                inv.data[i][j] = aug.data[i][n + j]
        return inv

    def extract_rows(self, row_indices):
        result = GFMatrix(len(row_indices), self.cols, self.rs)
        for i, r in enumerate(row_indices):
            result.data[i] = list(self.data[r])
        return result

class ReedSolomon:
    """Generalized Reed-Solomon implementation using GF(2^8)."""
    def __init__(self):
        self.gf_log = [0] * 256
        self.gf_exp = [0] * 512
        self._precompute_tables()
        self._mul_tables = {} # Cache for fast bytearray translation

    def _precompute_tables(self):
        x = 1
        for i in range(255):
            self.gf_exp[i] = x
            self.gf_log[x] = i
            x <<= 1
            if x & 0x100:
                x ^= 0x11D # Primitive polynomial
        for i in range(255, 512):
            self.gf_exp[i] = self.gf_exp[i - 255]

    def gf_mul(self, a, b):
        if a == 0 or b == 0: return 0
        return self.gf_exp[self.gf_log[a] + self.gf_log[b]]

    def gf_div(self, a, b):
        if b == 0: raise ZeroDivisionError()
        if a == 0: return 0
        return self.gf_exp[self.gf_log[a] + 255 - self.gf_log[b]]

    def get_mul_table(self, scalar):
        """Returns a 256-byte translation table for fast chunk multiplication."""
        if scalar not in self._mul_tables:
            table = bytearray(256)
            for i in range(256):
                table[i] = self.gf_mul(scalar, i)
            self._mul_tables[scalar] = table
        return self._mul_tables[scalar]

    def build_generator_matrix(self, k, n):
        if n > 256: raise ValueError("n cannot exceed 256 for GF(2^8)")
        if k > n: raise ValueError("k cannot be greater than n")
        
        # 1. Vandermonde Matrix
        v = GFMatrix(n, k, self)
        for r in range(n):
            for c in range(k):
                # r^c in GF(2^8).  r=0 requires special handling.
                if r == 0:
                    v.data[r][c] = 1 if c == 0 else 0
                else:
                    val = 1
                    for _ in range(c): val = self.gf_mul(val, r)
                    v.data[r][c] = val
        
        # 2. Convert to Systematic Form (Top k rows are Identity)
        top_k = v.extract_rows(list(range(k)))
        top_k_inv = top_k.invert()
        return v.multiply(top_k_inv)

    def encode(self, data: bytes, k: int, n: int):
        if k > 10 or n > 15:
            raise ValueError("For performance, max k=10, max n=15.")
            
        padding_len = (k - (len(data) % k)) % k
        padded_data = data + (b'\x00' * padding_len)
        chunk_size = len(padded_data) // k
        
        data_chunks = [padded_data[i*chunk_size : (i+1)*chunk_size] for i in range(k)]
        generator = self.build_generator_matrix(k, n)
        
        # Bottom (n-k) rows are the parity matrix
        all_chunks = list(data_chunks)
        for i in range(k, n):
            parity_chunk = bytearray(chunk_size)
            for j in range(k):
                scalar = generator.data[i][j]
                if scalar == 0: continue
                # Fast bulk GF multiplication via translate table
                mapped = bytearray(data_chunks[j]).translate(self.get_mul_table(scalar))
                # Bulk XOR
                for x in range(chunk_size):
                    parity_chunk[x] ^= mapped[x]
            all_chunks.append(bytes(parity_chunk))
            
        return all_chunks, padding_len

    def decode(self, fragments: dict, k: int, n: int, original_size: int, padding_len: int):
        if len(fragments) < k:
            raise ValueError(f"Need at least {k} fragments, got {len(fragments)}")
            
        # Optimization: If we have all original data chunks, just concat
        indices = sorted(fragments.keys())[:k] # Take exactly k chunks
        if indices == list(range(k)):
            combined = b"".join([fragments[i] for i in indices])
            return combined[:len(combined)-padding_len]

        # General decode
        generator = self.build_generator_matrix(k, n)
        avail_matrix = generator.extract_rows(indices)
        decode_matrix = avail_matrix.invert()
        
        chunk_size = len(fragments[indices[0]])
        reconstructed = []
        
        for i in range(k):
            reconstructed_chunk = bytearray(chunk_size)
            for j in range(k):
                scalar = decode_matrix.data[i][j]
                if scalar == 0: continue
                src_chunk = fragments[indices[j]]
                mapped = bytearray(src_chunk).translate(self.get_mul_table(scalar))
                for x in range(chunk_size):
                    reconstructed_chunk[x] ^= mapped[x]
            reconstructed.append(bytes(reconstructed_chunk))
            
        combined = b"".join(reconstructed)
        return combined[:len(combined)-padding_len]
