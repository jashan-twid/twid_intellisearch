import re

with open("contacts/user40321617.vcf", "r") as f:
    lines = f.readlines()

def clean_number(num):
    # Remove spaces, dashes, and leading +91
    num = num.replace(" ", "").replace("-", "")
    if num.startswith("+91"):
        num = num[3:]
    # Keep only digits, then last 10 digits
    digits = re.sub(r"\\D", "", num)
    return digits[-10:] if len(digits) >= 10 else digits

with open("contacts/user40321617.vcf", "w") as f:
    for line in lines:
        if line.startswith("TEL;CELL:"):
            number = line.split(":", 1)[1].strip()
            cleaned = clean_number(number)
            f.write(f"TEL;CELL:{cleaned}\n")
        else:
            f.write(line)