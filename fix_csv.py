import csv
with open('data/shlokas.csv', 'r', newline='', encoding='utf-8') as infile, open('data/shlokas_fixed.csv', 'w', newline='', encoding='utf-8') as outfile:
    reader = csv.reader(infile)
    writer = csv.writer(outfile, quoting=csv.QUOTE_MINIMAL)
    for row in reader:
        new_row = []
        for field in row:
            if ',' in field:
                new_row.append('"' + field + '"')
            else:
                new_row.append(field)
        writer.writerow(new_row)
import os
os.replace('data/shlokas_fixed.csv', 'data/shlokas.csv')