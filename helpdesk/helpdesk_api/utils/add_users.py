import csv
from helpdesk_api.models import User

def func(file_path):
    users = []

    with open(file_path, newline='', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            email = row['Email Address']
            first_name = row['First name']
            last_name = row['Last Name']
            floor = row['Floor']
            department = row['Unit/Department']

            print(f"Email: {email}, First Name: {first_name}, Last Name: {last_name}, Floor: {floor}, Department: {department}")

            user = User(
                email=email,
                first_name=first_name,
                last_name=last_name,
                floor=floor,
                department=department,
            )
            user.set_unusable_password()
            users.append(user)

    User.objects.bulk_create(users, batch_size=100)
    print(f"Successfully added {len(users)} users.")