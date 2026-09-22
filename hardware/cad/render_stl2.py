import trimesh
import numpy as np
import pyrender

path = r"C:\Users\user\Downloads\toy_robot_enclosure.main_design.stl"
mesh = trimesh.load(path)
mesh.visual.face_colors = [180, 200, 220, 255]

scene = pyrender.Scene(bg_color=[30, 30, 30, 255], ambient_light=[0.4, 0.4, 0.4])
pr_mesh = pyrender.Mesh.from_trimesh(mesh, smooth=False)
scene.add(pr_mesh)

light = pyrender.DirectionalLight(color=np.ones(3), intensity=4.0)

center = mesh.bounding_box.centroid
extent = mesh.bounding_box.extents.max()
dist = extent * 1.8

def look_from(offset):
    cam_pos = center + np.array(offset) * dist
    forward = (center - cam_pos)
    forward = forward / np.linalg.norm(forward)
    up = np.array([0, 0, 1.0]) if abs(forward[2]) < 0.9 else np.array([0, 1.0, 0])
    right = np.cross(forward, up)
    right = right / np.linalg.norm(right)
    true_up = np.cross(right, forward)
    mat = np.eye(4)
    mat[:3, 0] = right
    mat[:3, 1] = true_up
    mat[:3, 2] = -forward
    mat[:3, 3] = cam_pos
    return mat

views = {
    "front": (0, -1, 0.3),
    "back": (0, 1, 0.3),
    "top": (0, 0.01, 1),
    "iso": (1, -1, 1),
}

r = pyrender.OffscreenRenderer(900, 900)
for name, offset in views.items():
    cam = pyrender.PerspectiveCamera(yfov=np.pi / 4.0)
    cam_pose = look_from(offset)
    cam_node = scene.add(cam, pose=cam_pose)
    light_node = scene.add(light, pose=cam_pose)
    color, depth = r.render(scene)
    import imageio
    imageio.imwrite(f"docs/sparky_shopping_list_images/_stl2_{name}.png", color)
    scene.remove_node(cam_node)
    scene.remove_node(light_node)

print("Done")
