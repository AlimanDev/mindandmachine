import pandas as pd
import os

path_to_folder = '/Users/alex/Downloads/res 2'

list_of_folders = os.listdir(path=path_to_folder)

df_total = pd.DataFrame(columns=[0])
for folder in list_of_folders:
    if not folder.startswith('.') and folder:
        list_of_name = []
        list_of_files = os.listdir(path_to_folder + '/' + folder)
        df = pd.DataFrame()
        for file_ind, csv_name in enumerate(list_of_files):
            try:
                # print(csv_name)
                df = df.append(pd.read_csv(path_to_folder + '/' + folder + '/' + csv_name, header=None, sep=';'), ignore_index=True)

                # if file_ind == 20:
                #     import pdb
                #     pdb.set_trace()
                # df['folder_name'] = folder

                # df.to_csv('foo.csv', mode='a', index=False, header=False, sep=';')
            except pd.errors.EmptyDataError as e:
                # print(e)
                pass

        df = df.drop(columns=2).rename(columns={1: folder})
        df_total = df_total.merge(df, how='outer', on=0)
        print('add', folder)
df_total
