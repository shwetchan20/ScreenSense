"""Download OmniParser trained weights from Hugging Face"""

import os
import sys
from pathlib import Path

try:
    from huggingface_hub import hf_hub_download
except ImportError:
    print("Installing huggingface_hub...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "huggingface_hub"])
    from huggingface_hub import hf_hub_download

def download_omniparser_weights():
    """Download OmniParser icon detection weights"""
    
    print("=" * 60)
    print("Downloading OmniParser Trained Weights")
    print("=" * 60)
    print()
    
    # Create weights directory
    weights_dir = Path("weights/omniparser")
    weights_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"📁 Weights directory: {weights_dir.absolute()}")
    print()
    
    # Try downloading from OmniParser-v2.0 repo
    print("📥 Downloading icon detection model...")
    print("   Repository: microsoft/OmniParser-v2.0")
    print("   Trying multiple file paths...")
    print()
    
    # Possible file paths
    file_paths = [
        "icon_detect/model.pt",
        "icon_detect/best.pt",
        "weights/icon_detect/best.pt",
        "model.pt",
        "best.pt",
    ]
    
    model_path = None
    for file_path in file_paths:
        try:
            print(f"   Trying: {file_path}...")
            model_path = hf_hub_download(
                repo_id="microsoft/OmniParser-v2.0",
                filename=file_path,
                local_dir=weights_dir,
                local_dir_use_symlinks=False,
            )
            print(f"   ✅ Found!")
            break
        except Exception as e:
            print(f"   ❌ Not found")
            continue
    
    if not model_path:
        print()
        print("❌ Could not download from Hugging Face")
        print()
        print("Alternative: Use YOLOv8 pre-trained model (works but not UI-specific)")
        print("The system will use standard YOLOv8n which can detect general objects.")
        print()
        return False
    
    print()
    print(f"✅ Downloaded to: {model_path}")
    print()
    
    # Update .env with model path
    env_path = Path(".env")
    if env_path.exists():
        with open(env_path, "r") as f:
            lines = f.readlines()
        
        # Update OMNIPARSER_MODEL_PATH
        updated = False
        for i, line in enumerate(lines):
            if line.startswith("OMNIPARSER_MODEL_PATH="):
                lines[i] = f"OMNIPARSER_MODEL_PATH={model_path}\n"
                updated = True
                break
        
        if updated:
            with open(env_path, "w") as f:
                f.writelines(lines)
            print("✅ Updated .env with model path")
        else:
            print("⚠️  Could not find OMNIPARSER_MODEL_PATH in .env")
            print(f"   Please add: OMNIPARSER_MODEL_PATH={model_path}")
    
    print()
    print("=" * 60)
    print("✅ OmniParser weights downloaded successfully!")
    print("=" * 60)
    print()
    print("Next steps:")
    print("1. Restart ARIA: python -m screensense.app")
    print("2. Watch for: [OmniParser] Initialized successfully")
    print("3. You should see: [LocalQwen] OmniParser detected X elements (X > 0)")
    print()
    
    return True

if __name__ == "__main__":
    success = download_omniparser_weights()
    sys.exit(0 if success else 1)
