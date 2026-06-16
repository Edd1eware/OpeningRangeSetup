import glob
import os

RESULTS_FOLDER = r"C:\Users\k_99_\Desktop\codding\data_footprint_generator\trade_results_score"

def delete_excel_files():
    patterns = ["*.xlsx", "*.xls", "*.xlsm"]
    deleted = 0
    for pattern in patterns:
        for path in glob.glob(os.path.join(RESULTS_FOLDER, pattern)):
            os.remove(path)
            print(f"Deleted: {os.path.basename(path)}")
            deleted += 1
    print(f"\nTotal deleted: {deleted} Excel files.")

if __name__ == "__main__":
    delete_excel_files()
