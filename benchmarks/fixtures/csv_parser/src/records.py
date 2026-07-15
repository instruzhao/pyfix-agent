def parse_record(line):
    name, city = line.strip().split(",")
    return {"name": name, "city": city}
