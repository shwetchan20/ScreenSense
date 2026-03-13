"""Test script for verified perception pipeline"""

import time
import numpy as np
from src.screensense.perception import (
    OmniParserClient,
    WindowsUIAAdapter,
    CrossModalComparator,
    ContextAssembler,
    PassiveContextCollector,
    WindowMetadata,
)


def test_perception_pipeline():
    """Test the complete verified perception pipeline"""
    print("=== Testing Verified Perception Pipeline ===\n")
    
    # Initialize components
    print("1. Initializing components...")
    omniparser = OmniParserClient(device="cpu")
    uia_adapter = WindowsUIAAdapter(cache_ttl_seconds=0.5, max_depth=5)
    comparator = CrossModalComparator(position_tolerance=20)
    context_assembler = ContextAssembler(max_tokens=4000)
    passive_collector = PassiveContextCollector()
    
    print("   ✓ All components initialized\n")
    
    # Create dummy frame
    print("2. Creating test frame...")
    frame_rgb = np.random.randint(0, 255, (1080, 1920, 3), dtype=np.uint8)
    print("   ✓ Test frame created (1920x1080)\n")
    
    # Test OmniParser
    print("3. Testing OmniParser detection...")
    omni_elements = omniparser.detect_elements(frame_rgb)
    print(f"   ✓ OmniParser detected {len(omni_elements)} elements\n")
    
    # Test UIA
    print("4. Testing Windows UIA extraction...")
    uia_elements = uia_adapter.get_accessibility_tree()
    print(f"   ✓ UIA extracted {len(uia_elements)} elements\n")
    
    # Test cross-modal comparison
    print("5. Testing cross-modal comparison...")
    verified_elements = comparator.compare_elements(omni_elements, uia_elements)
    high_conf = sum(1 for e in verified_elements if e.confidence.value == "high")
    low_conf = sum(1 for e in verified_elements if e.confidence.value == "low")
    print(f"   ✓ Verified {len(verified_elements)} elements")
    print(f"     - HIGH confidence: {high_conf}")
    print(f"     - LOW confidence: {low_conf}\n")
    
    # Test passive signals
    print("6. Testing passive context collection...")
    window_meta = WindowMetadata(
        process_name="python.exe",
        window_title="Test Window",
        pid=12345,
        timestamp=time.time(),
    )
    passive_signals = passive_collector.collect(window_meta)
    print(f"   ✓ Passive signals collected")
    print(f"     - Clipboard: {passive_signals.clipboard_content is not None}")
    print(f"     - Browser URL: {passive_signals.browser_url is not None}")
    print(f"     - Recent files: {len(passive_signals.recent_files)}\n")
    
    # Test context assembly
    print("7. Testing context assembly...")
    rich_context = context_assembler.assemble_context(
        verified_elements=verified_elements,
        passive_signals=passive_signals,
        session_goal="Testing verified perception",
        user_name="Test User",
        project_name="ScreenSense",
    )
    print(f"   ✓ Rich context assembled")
    print(f"     - Total elements: {len(rich_context.verified_elements)}")
    print(f"     - High confidence: {rich_context.high_confidence_count()}")
    print(f"     - Low confidence: {rich_context.low_confidence_count()}\n")
    
    # Test serialization
    print("8. Testing LLM serialization...")
    serialized = context_assembler.serialize_for_llm(rich_context)
    token_count = context_assembler.count_tokens(serialized)
    print(f"   ✓ Context serialized")
    print(f"     - Length: {len(serialized)} chars")
    print(f"     - Estimated tokens: {token_count}\n")
    
    print("=== All Tests Passed! ===\n")
    print("Sample serialized context (first 500 chars):")
    print("-" * 60)
    print(serialized[:500])
    print("-" * 60)


if __name__ == "__main__":
    try:
        test_perception_pipeline()
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
