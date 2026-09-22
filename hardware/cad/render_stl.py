import trimesh
import numpy as np

path = r"C:\Users\user\Downloads\toy_robot_enclosure.main_design.stl"
mesh = trimesh.load(path)

try:
    scene = mesh.scene()
    angles = {
        "front": (0, 0, 0),
        "iso": (np.radians(30), np.radians(45), 0),
        "top": (np.radians(90), 0, 0),
    }
    for name, (rx, ry, rz) in angles.items():
        scene.set_camera(angles=(rx, ry, rz), distance=mesh.bounding_box.extents.max() * 2.2)
        png = scene.save_image(resolution=(900, 900))
        with open(f"docs/sparky_shopping_list_images/_stl_{name}.png", "wb") as f:
            f.write(png)
    print("Rendered via pyrender backend")
except Exception as e:
    print("pyrender path failed:", e)
    print("Falling back to matplotlib wireframe render")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection

    for name, elev, azim in [("front", 0, -90), ("iso", 25, -60), ("top", 90, -90)]:
        fig = plt.figure(figsize=(8, 8))
        ax = fig.add_subplot(111, projection="3d")
        tris = mesh.vertices[mesh.faces]
        collection = Poly3DCollection(tris, facecolor="lightsteelblue", edgecolor="k", linewidths=0.05, alpha=0.9)
        ax.add_collection3d(collection)
        bounds = mesh.bounds
        ax.set_xlim(bounds[0][0], bounds[1][0])
        ax.set_ylim(bounds[0][1], bounds[1][1])
        ax.set_zlim(bounds[0][2], bounds[1][2])
        ax.set_box_aspect(tuple(float(v) for v in mesh.bounding_box.extents))
        ax.view_init(elev=elev, azim=azim)
        ax.set_axis_off()
        plt.tight_layout()
        plt.savefig(f"docs/sparky_shopping_list_images/_stl_{name}.png", dpi=120)
        plt.close(fig)
    print("Rendered via matplotlib fallback")
