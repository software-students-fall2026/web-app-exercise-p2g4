from app import DINING_HALLS, dining_halls_collection, make_slug

DINING_HALL_DATA = [
    {
        "name": "Downstein",
        "description": "Description coming soon.",
        "hours": "Hours to be added.",
        "building": "Building to be added.",
        "address": "New York, NY",
        "image_file": "",
    },
    {
        "name": "ThirdNorth",
        "description": "Description coming soon.",
        "hours": "Hours to be added.",
        "building": "Building to be added.",
        "address": "New York, NY",
        "image_file": "",
    },
    {
        "name": "Lipton",
        "description": "Description coming soon.",
        "hours": "Hours to be added.",
        "building": "Building to be added.",
        "address": "New York, NY",
        "image_file": "",
    },
    {
        "name": "Kosher Cafe",
        "description": "Description coming soon.",
        "hours": "Hours to be added.",
        "building": "Building to be added.",
        "address": "New York, NY",
        "image_file": "",
    },
    {
        "name": "Kimmel",
        "description": "Description coming soon.",
        "hours": "Hours to be added.",
        "building": "Building to be added.",
        "address": "New York, NY",
        "image_file": "",
    },
    {
        "name": "JasperKane",
        "description": "Description coming soon.",
        "hours": "Hours to be added.",
        "building": "Building to be added.",
        "address": "New York, NY",
        "image_file": "",
    },
    {
        "name": "Palladium",
        "description": "Description coming soon.",
        "hours": "Hours to be added.",
        "building": "Building to be added.",
        "address": "New York, NY",
        "image_file": "",
    },
    {
        "name": "Upstein",
        "description": "Description coming soon.",
        "hours": "Hours to be added.",
        "building": "Building to be added.",
        "address": "New York, NY",
        "image_file": "",
    },
    {
        "name": "Crave",
        "description": "Description coming soon.",
        "hours": "Hours to be added.",
        "building": "Building to be added.",
        "address": "New York, NY",
        "image_file": "",
    },
    {
        "name": "Flaovr Lab",
        "description": "Description coming soon.",
        "hours": "Hours to be added.",
        "building": "Building to be added.",
        "address": "New York, NY",
        "image_file": "",
    },
    {
        "name": "Cafe 181",
        "description": "Description coming soon.",
        "hours": "Hours to be added.",
        "building": "Building to be added.",
        "address": "New York, NY",
        "image_file": "",
    },
    {
        "name": "Cafe 370",
        "description": "Description coming soon.",
        "hours": "Hours to be added.",
        "building": "Building to be added.",
        "address": "New York, NY",
        "image_file": "",
    },
]


def check_names():
    seed_names = []
    for hall in DINING_HALL_DATA:
        seed_names.append(hall["name"])

    problems = []

    for name in DINING_HALLS:
        if name not in seed_names:
            problems.append(f"Missing from seed data: {name}")

    for name in seed_names:
        if name not in DINING_HALLS:
            problems.append(f"Not in DINING_HALLS: {name}")

    return problems


def main():
    problems = check_names()

    if problems:
        print("Seeding stopped. Fix these names first:")
        for problem in problems:
            print(" -", problem)
        return

    for hall in DINING_HALL_DATA:
        slug = make_slug(hall["name"])

        dining_halls_collection.update_one(
            {"slug": slug},
            {
                "$set": {
                    "slug": slug,
                    "name": hall["name"],
                    "description": hall["description"],
                    "hours": hall["hours"],
                    "building": hall["building"],
                    "address": hall["address"],
                    "image_file": hall["image_file"],
                }
            },
            upsert=True,
        )

        print(f"Saved: {hall['name']} -> {slug}")

    total = dining_halls_collection.count_documents({})
    print(f"Done. dining_halls now has {total} documents.")


if __name__ == "__main__":
    main()