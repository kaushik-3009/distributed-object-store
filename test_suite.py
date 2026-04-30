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
            resp = requests.post(
                f"{COORDINATOR_URL}/upload/", 
                files={"file": (self.file_name, f)},
                data={"k": 2, "n": 3}
            )
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
            requests.post(
                f"{COORDINATOR_URL}/upload/", 
                files={"file": (self.file_name, f)},
                data={"k": 2, "n": 3}
            )
        
        # 2. Corrupt one node that actually holds a chunk for this file
        topology = requests.get(f"{COORDINATOR_URL}/admin/topology").json()
        num_nodes = len(topology)
        
        corrupted = 0
        for node_id in range(1, num_nodes + 1):
            resp = requests.post(f"{COORDINATOR_URL}/admin/corrupt/{node_id}/{self.file_name}")
            if resp.status_code == 200:
                print(f"  => Corrupted chunk on Node {node_id}.")
                corrupted += 1
                if corrupted == 1:
                    break
                    
        self.assertEqual(corrupted, 1, "Failed to corrupt any node (could not find a matching chunk)")

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
            requests.post(
                f"{COORDINATOR_URL}/upload/", 
                files={"file": (self.file_name, f)},
                data={"k": 2, "n": 3}
            )
        
        # 2. Corrupt two nodes that hold chunks for this file
        topology = requests.get(f"{COORDINATOR_URL}/admin/topology").json()
        num_nodes = len(topology)
        
        corrupted = 0
        for node_id in range(1, num_nodes + 1):
            resp = requests.post(f"{COORDINATOR_URL}/admin/corrupt/{node_id}/{self.file_name}")
            if resp.status_code == 200:
                print(f"  => Corrupted chunk on Node {node_id}.")
                corrupted += 1
                if corrupted == 2:
                    break
                    
        self.assertEqual(corrupted, 2, "Failed to corrupt two nodes (could not find chunks)")

        # 3. Download (Should fail with 500 Error)
        resp = requests.get(f"{COORDINATOR_URL}/download/{self.file_name}")
        self.assertEqual(resp.status_code, 500)
        self.assertIn("Not enough valid fragments", resp.json()['detail'])
        print("  => OK: System correctly identified that data is unrecoverable.")

if __name__ == "__main__":
    unittest.main()
