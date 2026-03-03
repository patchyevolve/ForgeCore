"""Remove duplicate functions from main.cpp"""

target_file = r"D:\codeWorks\graphicstics\graphicstuff\main.cpp"

with open(target_file, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Remove all test functions
cleaned_lines = []
skip_until_brace = False
test_functions = ['test_sync_func', 'baseline_test_func', 'normal_add_func', 
                  'staging_test', 'integrity_test', 'helper_function']

for line in lines:
    # Check if this line contains any test function
    if any(func in line for func in test_functions):
        skip_until_brace = True
        continue
    
    if skip_until_brace:
        if '}' in line:
            skip_until_brace = False
        continue
    
    cleaned_lines.append(line)

with open(target_file, 'w', encoding='utf-8') as f:
    f.writelines(cleaned_lines)

print("Cleaned up all test functions")
print("File reset to clean state")
