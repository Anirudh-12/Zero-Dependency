import os
import subprocess
import shutil
import hashlib
from pathlib import Path

def run_build(env):
    """Run uv build and return True if successful."""
    print("Running 'uv build'...")
    # Run uv build, ensure it works cross-platform
    # On Windows it might need shell=True if uv is a batch script, but usually uv.exe is available
    result = subprocess.run(["uv", "build"], env=env, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Build failed:\n{result.stderr}")
        return False
    return True

def get_dist_hashes():
    """Calculate SHA256 hashes of all files in the dist/ directory."""
    dist_dir = Path("dist")
    if not dist_dir.exists() or not dist_dir.is_dir():
        print("dist/ directory not found.")
        return {}
    
    hashes = {}
    for filepath in sorted(dist_dir.glob("*.whl")):
        sha256_hash = hashlib.sha256()
        with open(filepath, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        hashes[filepath.name] = sha256_hash.hexdigest()
    return hashes

def clean_dist():
    """Remove the dist/ directory."""
    dist_dir = Path("dist")
    if dist_dir.exists():
        shutil.rmtree(dist_dir)

def main():
    print("=== PyXRay Reproducible Build Verification ===")
    
    # 1. Prepare environment
    env = os.environ.copy()
    env["SOURCE_DATE_EPOCH"] = "1704067200"
    
    # 2. Build 1
    print("\n--- Build 1 ---")
    clean_dist()
    if not run_build(env):
        return
    hashes_build1 = get_dist_hashes()
    if not hashes_build1:
        print("No files found after Build 1.")
        return
    
    for filename, h in hashes_build1.items():
        print(f"{filename}: {h}")

    # 3. Build 2
    print("\n--- Build 2 ---")
    clean_dist()
    if not run_build(env):
        return
    hashes_build2 = get_dist_hashes()
    if not hashes_build2:
        print("No files found after Build 2.")
        return
    
    for filename, h in hashes_build2.items():
        print(f"{filename}: {h}")

    # 4. Compare
    print("\n--- Comparison ---")
    if hashes_build1 == hashes_build2:
        print("✅ Success! The builds are byte-identical.")
        for filename in hashes_build1:
            print(f"  {filename}: Match")
    else:
        print("❌ Failure! The builds differ.")
        all_files = set(hashes_build1.keys()) | set(hashes_build2.keys())
        for filename in all_files:
            h1 = hashes_build1.get(filename, "MISSING")
            h2 = hashes_build2.get(filename, "MISSING")
            if h1 == h2:
                print(f"  {filename}: Match")
            else:
                print(f"  {filename}: MISMATCH")
                print(f"    Build 1: {h1}")
                print(f"    Build 2: {h2}")

if __name__ == "__main__":
    main()
