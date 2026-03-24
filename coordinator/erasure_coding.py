import numpy as np

class ReedSolomon:
    """
    A simple Reed-Solomon implementation using GF(2^8).
    For learning purposes, we'll use a standard primitive polynomial: x^8 + x^4 + x^3 + x^2 + 1 (0x11D).
    """
    def __init__(self, k, n):
        self.k = k # Number of data fragments
        self.n = n # Total fragments (data + parity)
        self.m = n - k # Number of parity fragments
        
        # Precompute log and antilog tables for fast multiplication
        self.gf_log = [0] * 256
        self.gf_exp = [0] * 512
        self._precompute_tables()

    def _precompute_tables(self):
        x = 1
        for i in range(255):
            self.gf_exp[i] = x
            self.gf_log[x] = i
            # Galois Field multiplication by 2
            x <<= 1
            if x & 0x100:
                x ^= 0x11D # Primitive polynomial
        for i in range(255, 512):
            self.gf_exp[i] = self.gf_exp[i - 255]

    def gf_mul(self, a, b):
        if a == 0 or b == 0:
            return 0
        return self.gf_exp[self.gf_log[a] + self.gf_log[b]]

    def gf_div(self, a, b):
        if b == 0:
            raise ZeroDivisionError()
        if a == 0:
            return 0
        return self.gf_exp[self.gf_log[a] + 255 - self.gf_log[b]]

    def encode(self, data: bytes):
        """
        Splits data into k chunks and generates n-k parity chunks.
        """
        # 1. Padding: Ensure data length is a multiple of k
        padding_len = (self.k - (len(data) % self.k)) % self.k
        padded_data = data + (b'\x00' * padding_len)
        
        chunk_size = len(padded_data) // self.k
        chunks = [list(padded_data[i*chunk_size : (i+1)*chunk_size]) for i in range(self.k)]
        
        # 2. Simple Parity (for k=2, n=3, this is basically XOR-like but in GF)
        # In a full Reed-Solomon, we'd use a Vandermonde matrix. 
        # For our specific k=2, n=3 goal, let's implement the parity: P = D1 + D2 (in GF)
        parity_chunks = []
        for i in range(self.m):
            p_chunk = []
            for j in range(chunk_size):
                # Simple example: Parity is the sum (XOR) of data chunks
                # In GF(2^8), addition is just XOR.
                val = chunks[0][j] ^ chunks[1][j] 
                p_chunk.append(val)
            parity_chunks.append(p_chunk)
            
        return [bytes(c) for c in chunks] + [bytes(p) for p in parity_chunks], padding_len

    def decode(self, fragments: dict, original_size: int, padding_len: int):
        """
        fragments: dict mapping index (0 to n-1) to bytes.
        Needs at least k fragments to work.
        """
        if len(fragments) < self.k:
            raise ValueError("Not enough fragments to reconstruct")

        # Sort fragment indices
        indices = sorted(fragments.keys())
        
        # Case 1: We have both data chunks (Indices 0 and 1)
        if 0 in fragments and 1 in fragments:
            combined = fragments[0] + fragments[1]
            return combined[:len(combined)-padding_len]

        # Case 2: We are missing one data chunk but have the parity chunk (Index 2)
        # Since P = D1 + D2, then D1 = P - D2 and D2 = P - D1.
        # In GF(2^8), addition and subtraction are both XOR.
        chunk_size = len(next(iter(fragments.values())))
        if 0 in fragments and 2 in fragments:
            # Missing D2. D2 = P ^ D1
            d2 = bytes([fragments[2][i] ^ fragments[0][i] for i in range(chunk_size)])
            combined = fragments[0] + d2
            return combined[:len(combined)-padding_len]
        
        if 1 in fragments and 2 in fragments:
            # Missing D1. D1 = P ^ D2
            d1 = bytes([fragments[2][i] ^ fragments[1][i] for i in range(chunk_size)])
            combined = d1 + fragments[1]
            return combined[:len(combined)-padding_len]

        raise ValueError("Reconstruction logic failed")
