import pandas as pd
import os

path_to_folder = '/Users/ruslan/Downloads/for_parse/'

list_of_folders = os.listdir(path=path_to_folder)

for folder in list_of_folders:
    if not folder.startswith('.') and folder:
        list_of_name = []
        list_of_files = os.listdir(path_to_folder + '/' + folder)
        for csv_name in list_of_files:
            try:
                print(csv_name)
                df = pd.read_csv(path_to_folder + '/' + folder + '/' + csv_name, header=None, sep=';')
                df['folder_name'] = folder
                df = df.drop(columns=2)
                df.to_csv('foo.csv', mode='a', index=False, header=False, sep=';')
            except Exception as e:
                print(e)
