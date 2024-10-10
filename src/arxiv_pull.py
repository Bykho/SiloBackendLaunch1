import os
import json
from pymongo import MongoClient, UpdateOne, TEXT
from tqdm import tqdm  # For progress bar
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# MongoDB connection setup
MONGO_URI = os.environ.get('MONGO_URI')
mongo_client = MongoClient(MONGO_URI)
db = mongo_client['arxiv_database']
collection = db['arxiv_collection']

# Ensure indexes for text search and unique IDs
collection.create_index(
    [('title', TEXT), ('abstract', TEXT), ('authors', TEXT)],
    default_language='english'
)
collection.create_index('arxiv_id', unique=True)
print("Indexes created")

def parse_and_insert(metadata_file):
    with open(metadata_file, 'r') as f:
        operations = []
        count = 0
        for line in tqdm(f, desc='Processing records'):
            try:
                record = json.loads(line)
                arxiv_id = record.get('id')
                title = record.get('title')
                abstract = record.get('abstract')
                authors = record.get('authors')
                authors_parsed = record.get('authors_parsed')

                # Handle authors
                if authors_parsed:
                    # Each author is [last_name, first_name, suffix]
                    authors_list = [
                        ' '.join(filter(None, [author[1], author[0], author[2]]))
                        for author in authors_parsed
                    ]
                else:
                    # If authors_parsed is not available, split 'authors' string
                    authors_list = [author.strip() for author in authors.split(',')]

                # Other fields
                categories = record.get('categories')
                comments = record.get('comments')
                journal_ref = record.get('journal-ref')
                doi = record.get('doi')
                report_no = record.get('report-no')
                license = record.get('license')
                submitter = record.get('submitter')
                versions = record.get('versions')
                update_date = record.get('update_date')

                # Construct links
                link = f'https://arxiv.org/abs/{arxiv_id}'
                pdf_link = f'https://arxiv.org/pdf/{arxiv_id}.pdf'

                document = {
                    'arxiv_id': arxiv_id,
                    'title': title,
                    'abstract': abstract,
                    'authors': authors_list,
                    'categories': categories,
                    'comments': comments,
                    'journal_ref': journal_ref,
                    'doi': doi,
                    'report_no': report_no,
                    'license': license,
                    'submitter': submitter,
                    'versions': versions,
                    'update_date': update_date,
                    'link': link,
                    'pdf_link': pdf_link
                }

                operations.append(
                    UpdateOne({'arxiv_id': arxiv_id}, {'$set': document}, upsert=True)
                )
                count += 1

                # Execute batch insert every 1000 records
                if len(operations) == 1000:
                    collection.bulk_write(operations, ordered=False)
                    operations = []

            except Exception as e:
                print(f'Error processing record: {e}')

        # Insert any remaining operations
        if operations:
            collection.bulk_write(operations, ordered=False)

    print(f'Done. {count} records processed.')

# Specify the path to your metadata file
metadata_file = 'arxiv-metadata-oai-snapshot.json'
parse_and_insert(metadata_file)
