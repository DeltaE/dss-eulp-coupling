import os
root = r"D:\lvg\GSO\urban-suburban\parquet_data"
entries = os.listdir(root)
loose = [f for f in entries if f.endswith(".parquet")]
subdirs = [d for d in entries if os.path.isdir(os.path.join(root, d))]
print(f"native loose .parquet at root: {len(loose)}  e.g. {loose[:4]}")
for d in subdirs:
    fs = [f for f in os.listdir(os.path.join(root, d)) if f.endswith(".parquet")]
    print(f"  {d}: {len(fs)} parquet  e.g. {fs[:3]}")