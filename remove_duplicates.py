#!/usr/bin/env python3
"""Remove duplicate helper methods from controller.py"""

with open('core/controller.py', 'r') as f:
    lines = f.readlines()

print(f"Original file: {len(lines)} lines")

# Remove lines 776-940 (0-indexed: 775-939)
new_lines = lines[:775] + lines[940:]

print(f"After removing duplicates: {len(new_lines)} lines")
print(f"Removed: {len(lines) - len(new_lines)} lines")

with open('core/controller.py', 'w') as f:
    f.writelines(new_lines)

print("Done!")
