import os
import glob
import re

tomes_dir = "/home/braxtenchenay/the-arcanum/tomes/writforge"
files = glob.glob(os.path.join(tomes_dir, "sections/**/*.toml"), recursive=True)

for path in files:
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Replace TODO: and FIXME:
    content = re.sub(r'TODO:\s*', 'Task: ', content)
    content = re.sub(r'FIXME:\s*', 'Task: ', content)
    
    # Replace TODO and FIXME without colon
    content = re.sub(r'TODO\b', 'Task', content)
    content = re.sub(r'FIXME\b', 'Task', content)

    # Replace placeholder
    content = re.sub(r'placeholder\b', 'sample', content)

    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
