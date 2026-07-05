with open('frontend/ui/strings_fr.py', 'rb') as f:
    content = f.read()

# find where the valid content ends
idx = content.find(b'IMPORT_DONE_TOAST')
if idx != -1:
    end_idx = content.find(b'\n', idx)
    if end_idx != -1:
        valid = content[:end_idx+1]
        valid += b'\nACTION_CLOSE = "Fermer"\n'
        with open('frontend/ui/strings_fr.py', 'wb') as f:
            f.write(valid)
