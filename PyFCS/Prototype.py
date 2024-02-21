from scipy.spatial import Voronoi, voronoi_plot_2d
import numpy as np
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D

### my libraries ###
from PyFCS.geometry.Plane import Plane
from PyFCS.geometry.Point import Point
from PyFCS.geometry.GeometryTools import GeometryTools
from PyFCS.geometry.Face import Face
from PyFCS.geometry.Volume import Volume
from PyFCS.geometry.Vector import Vector

class Prototype:
    def __init__(self, label, positive, negatives):
        self.label = label
        self.positive = positive
        self.negatives = negatives

        # Create Voronoi volume
        self.voronoi_volume = self.create_voronoi_volume()




    def create_voronoi_volume(self):
        points = np.vstack((self.positive, self.negatives))
        voronoi = Voronoi(points, qhull_options='Fi Fo p Fv')

        # Extract regions and vertices
        regions, vertices = voronoi.regions, voronoi.vertices

        # Initialize faces array
        faces = {}

        # Iterate over bounded regions
        num_bounded = 0
        for i, region in enumerate(regions):
            if -1 in region:
                # Unbounded region, skip
                continue
            
            # Extract vertices of the region
            region_vertices = vertices[region]

            # Check if the region has enough vertices to form a face
            if len(region_vertices) >= 3:
                # Calculate normal vector (cross product of first three vertices)
                normal_vector = np.cross(region_vertices[1] - region_vertices[0], region_vertices[2] - region_vertices[0])

                # Create plane from the first three vertices
                plane = Plane.from_point_and_normal(Point(region_vertices[0][0], region_vertices[0][1], 0), Vector.from_array(normal_vector))

                # Store face in the faces dictionary
                faces[num_bounded] = Face(p=plane, bounded=True, vertex=region_vertices)
                num_bounded += 1

        # Iterate over unbounded regions
        num_unbounded = 0
        for i, region in enumerate(regions):
            if -1 not in region:
                # Bounded region, skip
                continue
            
            # Extract vertices of the region
            region_vertices = vertices[region]

            # Check if the region has enough vertices to form a face
            if len(region_vertices) >= 3:
                # Calculate normal vector (cross product of first three vertices)
                normal_vector = np.cross(region_vertices[1] - region_vertices[0], region_vertices[2] - region_vertices[0])

                # Create plane from the first three vertices
                plane = Plane.from_point_and_normal(Point(region_vertices[0][0], region_vertices[0][1], 0), Vector.from_array(normal_vector))

                # Store face in the faces dictionary
                faces[num_unbounded + num_bounded] = Face(p=plane, bounded=False, vertex=region_vertices)
                num_unbounded += 1

        # Create and return the voronoi volume
        representative = Point(*self.positive)
        voronoi_volume = self.face_to_volume(faces.values(), representative)





        # voronoi_proj = Voronoi(points[:, :2], qhull_options='Fi Fo p Fv')

        # # Visualization code
        # plt.figure(figsize=(8, 8))

        # # Plot Voronoi diagram
        # voronoi_plot_2d(voronoi_proj, show_vertices=False, line_colors='gray', line_width=2, line_alpha=0.6, point_size=10)

        # # Plot points used to generate Voronoi diagram
        # plt.scatter(points[:, 0], points[:, 1], c='red', marker='o', label='Centroids')

        # # Highlight positive centroid
        # plt.scatter(positive_centroid[0], positive_centroid[1], c='blue', marker='*', s=200, label='Positive Centroid')

        # plt.title('Voronoi Diagram')
        # plt.xlabel('X-axis')
        # plt.ylabel('Y-axis')
        # plt.legend()
        # plt.show()





        self.visualize_voronoi_2d(voronoi_volume)
        plt.close('all')


        return voronoi_volume

        



    def face_to_volume(self, faces, representative):
        volume = Volume(representative)

        for face in faces:
            volume.add_face(face)

        return volume


    def visualize_voronoi(self, volume):
        if volume is not None:
            # Extract information from the Volume object
            faces = volume.get_faces()

            # Extract vertices from faces
            all_vertices = []
            for face in faces:
                vertices = face.get_array_vertex()
                if vertices is not None and len(vertices) >= 3:
                    all_vertices.extend(vertices)


            # Visualization code
            fig = plt.figure(figsize=(8, 8))
            ax = fig.add_subplot(111, projection='3d')

            # Plot Voronoi diagram
            for face in faces:
                vertices = face.get_array_vertex()
                if vertices is not None and len(vertices) >= 3:
                    polygon = np.array(vertices)
                    ax.plot(polygon[:, 0], polygon[:, 1], polygon[:, 2], 'gray', linewidth=2, alpha=0.6)

            # Plot points used to generate Voronoi diagram
            ax.scatter(volume.representative.x, volume.representative.y, volume.representative.z, c='blue', marker='*', s=200, label='Positive Centroid')

            ax.set_title('Voronoi Diagram')
            ax.set_xlabel('X-axis')
            ax.set_ylabel('Y-axis')
            ax.set_zlabel('Z-axis')
            ax.legend()
            plt.show()
        else:
            print("No valid Voronoi regions found.")


    def visualize_voronoi_2d(self, volume):
        if volume is not None:
            # Extract information from the Volume object
            faces = volume.get_faces()

            # Visualization code
            fig, ax = plt.subplots(figsize=(8, 8))

            # Plot Voronoi diagram
            for face in faces:
                vertices = face.get_array_vertex()
                if vertices is not None and len(vertices) >= 3:
                    polygon = np.array(vertices)
                    ax.plot(polygon[:, 0], polygon[:, 1], 'gray', linewidth=2, alpha=0.6)

            # Plot points used to generate Voronoi diagram
            ax.scatter(volume.representative.x, volume.representative.y, c='blue', marker='*', s=200, label='Positive Centroid')

            ax.set_title('Voronoi Diagram')
            ax.set_xlabel('X-axis')
            ax.set_ylabel('Y-axis')
            ax.legend()
            plt.show()
        else:
            print("No valid Voronoi regions found.")