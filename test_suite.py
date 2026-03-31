import requests
import os
import unittest
import time

COORDINATOR_URL = "http://localhost:8000"
NODE1_URL = "http://localhost:8001"
NODE2_URL = "http://localhost:8002"
NODE3_URL = "http://localhost:8003"

class TestDistributedObjectStore(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Ensure the services are up. In a real CI/CD, we'd wait for /health
        print("\n--- Starting Distributed Store Test Suite ---")

    def setUp(self):
        self.file_name = f"test_file_{int(time.time())}.txt"
        self.content = b"This is test data for erasure coding verification." * 50
        with open(self.file_name, "wb") as f:
            f.write(self.content)

    def tearDown(self):
        if os.path.exists(self.file_name):
            os.remove(self.file_name)

    def test_01_upload_and_download_healthy(self):
        """Test 1: Normal upload and download works."""
        print("\n[Test] Upload and download (Healthy)...")
        with open(self.file_name, "rb") as f:
            resp = requests.post(f"{COORDINATOR_URL}/upload/", files={"file": (self.file_name, f)})
        self.assertEqual(resp.status_code, 200)

        resp = requests.get(f"{COORDINATOR_URL}/download/{self.file_name}")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.content, self.content)
        print("  => OK: File matches original.")

    def test_02_single_corruption_resilience(self):
        """Test 2: One node is corrupted, system should still recover data."""
        print("\n[Test] Single node corruption resilience...")
        # 1. Upload
        with open(self.file_name, "rb") as f:
            requests.post(f"{COORDINATOR_URL}/upload/", files={"file": (self.file_name, f)})
        
        # 2. Corrupt Node 3
        # We find the chunk ID by peeking at the local volume for the demo's sake
        chunk_id = self._get_chunk_id_from_node(3)
        resp = requests.post(f"{NODE3_URL}/corrupt/{chunk_id}")
        self.assertEqual(resp.status_code, 200)
        print(f"  => Corrupted {chunk_id} on Node 3.")

        # 3. Download (System should catch it and use Node 1 & 2 to rebuild)
        resp = requests.get(f"{COORDINATOR_URL}/download/{self.file_name}")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.content, self.content)
        print("  => OK: System successfully caught corruption and rebuilt file.")

    def test_03_double_corruption_failure(self):
        """Test 3: Two nodes are corrupted, system MUST fail (cannot reconstruct)."""
        print("\n[Test] Double node corruption detection...")
        # 1. Upload
        with open(self.file_name, "rb") as f:
            requests.post(f"{COORDINATOR_URL}/upload/", files={"file": (self.file_name, f)})
        
        # 2. Corrupt Node 2 AND Node 3
        chunk_id_2 = self._get_chunk_id_from_node(2)
        chunk_id_3 = self._get_chunk_id_from_node(3)
        requests.post(f"{NODE2_URL}/corrupt/{chunk_id_2}")
        requests.post(f"{NODE3_URL}/corrupt/{chunk_id_3}")
        print(f"  => Corrupted Node 2 and Node 3.")

        # 3. Download (Should fail with 500 Error)
        resp = requests.get(f"{COORDINATOR_URL}/download/{self.file_name}")
        self.assertEqual(resp.status_code, 500)
        self.assertIn("Not enough valid fragments", resp.json()['detail'])
        print("  => OK: System correctly identified that data is unrecoverable.")

    def _get_chunk_id_from_node(self, node_num):
        # In this local demo, the node data is shared via docker volumes.
        # We just look for the newest file in the node's data directory.
        data_dir = f"./node/data" 
        # Note: Since all nodes share the same code folder, we just look at the data folder.
        # In a real setup each node has its own volume.
        files = os.listdir(data_dir)
        # Sort by modification time to get the latest chunk we just uploaded
        files.sort(key=lambda x: os.path.getmtime(os.path.join(data_dir, x)), reverse=True)
        # Find a chunk that matches our latest upload index (e.g., chunk index 0, 1, or 2)
        # Our coordinator saves as {file_id}_{version_id}_{index}
        # For Node X, we look for suffix _(X-1)
        suffix = f"_{node_num-1}"
        for f in files:
            if f.endswith(suffix):
                return f
        return None

if __name__ == "__main__":
    unittest.main()
