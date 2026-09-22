import trimesh

path = r"C:\Users\user\Downloads\toy_robot_enclosure.main_design.stl"
mesh = trimesh.load(path)

print("Is watertight:", mesh.is_watertight)
print("Vertices:", len(mesh.vertices))
print("Faces:", len(mesh.faces))
print("Bounding box (mm):", mesh.bounding_box.extents)
print("Volume (mm^3):", mesh.volume)
