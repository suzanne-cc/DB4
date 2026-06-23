import os

file_path = None
storage_full = False
MIN_FREE_BYTES = 16384

def _free_bytes(path="data"):
    stat = os.statvfs(path)
    return stat[0] * stat[3]

def init_csv(file_name, data_names):
    global file_path, storage_full

    try:
        os.mkdir("data") # create data folder if it doesn't exist
    except OSError:
        pass  # folder already exists

    storage_full = False

    # create a new file if none exists yet
    if file_path is None:
        file_path = f"data/{file_name}.csv"
        with open(file_path, 'w') as f:
            f.write(",".join(data_names) + "\n")  # header row from data_names

def store_data(*values):
    global file_path, storage_full

    if storage_full:
        return  # stops logging

    line = ",".join(str(v) for v in values) + "\n"

    free = _free_bytes()
    if free is not None and free - len(line) < MIN_FREE_BYTES:
        storage_full = True
        print("Storage nearly full — stopped logging to prevent filesystem corruption")
        return

    try:
        with open(file_path, 'a') as f:
            f.write(line)
    except OSError as e:
        storage_full = True
        print(f"Storage write failed ({e}), stopped logging.")