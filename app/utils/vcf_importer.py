import os
from app.services.elasticsearch_manager import ElasticsearchManager



def parse_vcf_contacts(vcf_path):
    contacts = []

    with open(vcf_path, 'r') as f:
        contact = {}

        for line in f:
            line = line.strip()

            if line == 'BEGIN:VCARD':
                contact = {}
            elif line.startswith('FN:'):
                contact['name'] = line[3:]
            elif line.startswith('TEL'):
                # Handles TEL;TYPE=CELL:1234567890
                number = line.split(':')[-1]
                contact['number'] = number
            elif line == 'END:VCARD':
                if 'name' in contact and 'number' in contact:
                    contacts.append(contact)
                contact = {}

    return contacts



def import_all_user_contacts(contacts_dir, es_manager: ElasticsearchManager):
    for fname in os.listdir(contacts_dir):
        if fname.endswith('.vcf'):
            user_id = fname.replace('.vcf', '').replace('user', '')

            contacts = parse_vcf_contacts(os.path.join(contacts_dir, fname))

            if contacts:
                index = f'user_contacts_{user_id}'
                # Create index if not exists
                if not es_manager.es_client.indices.exists(index=index):
                    es_manager.es_client.indices.create(index=index, body={
                        "mappings": {
                            "properties": {
                                "name": {"type": "text"},
                                "number": {"type": "keyword"}
                            }
                        }
                    })

                # Bulk insert contacts
                for contact in contacts:
                    es_manager.es_client.index(index=index, body=contact)
