"""Clean up all test artifacts from main.cpp - keep ONLY main() function"""

import re

TARGET_FILE = r"D:\codeWorks\graphicstics\graphicstuff\main.cpp"

def clean_main_cpp():
    """Remove ALL functions except main() - keep includes and main only"""
    
    with open(TARGET_FILE, 'r', encoding='utf-8') as f:
        content = f.read()
    
    print(f"Original: {len(content)} bytes, {len(content.splitlines())} lines")
    
    lines = content.splitlines()
    result_lines = []
    
    # State tracking
    in_function = False
    in_main = False
    brace_count = 0
    
    for line in lines:
        stripped = line.strip()
        
        # Always keep includes and empty lines at the top
        if stripped.startswith('#include') or (not stripped and not in_function):
            result_lines.append(line)
            continue
        
        # Check if this line starts a function
        # Match: return_type function_name(...) or return_type function_name(...)
        func_match = re.match(r'^\s*\w+\s+(\w+)\s*\([^)]*\)\s*$', stripped)
        
        if func_match and not in_function:
            func_name = func_match.group(1)
            
            # Check if it's main
            if func_name == 'main':
                in_main = True
                in_function = True
                result_lines.append(line)
                continue
            else:
                # It's NOT main - start skipping
                in_function = True
                in_main = False
                brace_count = 0
                continue
        
        # If we're in a function
        if in_function:
            # Count braces
            brace_count += line.count('{') - line.count('}')
            
            # If in main, keep the line
            if in_main:
                result_lines.append(line)
            
            # Check if function ended
            if brace_count == 0 and ('{' in line or '}' in line):
                in_function = False
                in_main = False
            
            continue
        
        # Skip everything else (comments, test markers, etc.)
    
    cleaned = '\n'.join(result_lines)
    
    # Remove excessive blank lines
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
    
    # Ensure file ends with newline
    if not cleaned.endswith('\n'):
        cleaned += '\n'
    
    print(f"Cleaned: {len(cleaned)} bytes, {len(cleaned.splitlines())} lines")
    print(f"Removed: {len(content) - len(cleaned)} bytes")
    
    # Write cleaned content
    with open(TARGET_FILE, 'w', encoding='utf-8') as f:
        f.write(cleaned)
    
    print("\n✓ Cleanup complete! Only main() and includes remain.")


if __name__ == "__main__":
    print("="*60)
    print("CLEANING TEST ARTIFACTS")
    print("="*60)
    
    try:
        clean_main_cpp()
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
    
    print("="*60)
