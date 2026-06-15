import os

file_path = None

def init_csv(file_name, data_names):
    global file_path
    # create data folder if it doesn't exist
    try:
        os.mkdir("data")
    except OSError:
        pass  # folder already exists
    
    # create a new file if none exists yet
    if file_path is None:
        file_path = f"data/{file_name}.csv"
        with open(file_path, 'w') as f:
            f.write(",".join(data_names) + "\n")  # header row from data_names

def store_data(*values):
    global file_path

    with open(file_path, 'a') as f:
        f.write(",".join(str(v) for v in values) + "\n")