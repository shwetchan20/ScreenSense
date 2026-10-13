import pathlib
p = pathlib.Path(r'research\test_pipeline_integration.py')
content = p.read_text(encoding='utf-8')
old = '    icon = "\u2713" if status == PASS else "\u2717"'
new = '    icon = "PASS" if status == PASS else "FAIL"'
content = content.replace(old, new)
p.write_text(content, encoding='utf-8')
print("done, found=", old in p.read_text(encoding='utf-8'))
