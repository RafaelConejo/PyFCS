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
        self.voronoi_volume = self.create_voronoi_volumen()




    def create_voronoi_volumen(self):
        # if test == 'si':
        #     positive_centroid = centroids[center_index]
        #     negative = np.delete(centroids, center_index, axis=0)
        #     negative_centroids = np.vstack((negative, prototypes_neg))
        # elif test == 'no':
        #     positive_centroid = centroids[center_index]
        #     negative_centroids = np.delete(centroids, center_index, axis=0)


        points = np.vstack((self.positive, self.negatives))
        voronoi = Voronoi(points, qhull_options='Fi Fo p Fv')

        regions, vertices = voronoi.regions, voronoi.vertices
        valid_regions = regions # [region for region in regions if -1 not in region]

        faces = []

        if valid_regions:
            # Iterate through the valid_regions and create Face instances
            for region_index in range(len(valid_regions)):
                region = valid_regions[region_index]
                # Filter out -1 indices (infinitos)
                region_vertices = [vertices[i] for i in region if i != -1]

                # Check if the region has enough vertices to create a face
                if len(region_vertices) >= 3:
                    # Assume the normal vector of the plane points outward
                    normal_vector = np.cross(region_vertices[1] - region_vertices[0], region_vertices[2] - region_vertices[0])

                    # Create a Plane instance using the first three vertices of the region
                    plane = Plane.from_point_and_normal(Point(region_vertices[0][0], region_vertices[0][1], region_vertices[0][2]), Vector.from_array(normal_vector))

                    # Create a Face instance using the vertices and the created plane
                    face = Face(p=plane)
                    face.set_array_vertex(region_vertices)

                    faces.append(face)

            representative = Point(*self.positive)
            voronoi_volume = self.face_to_volume(faces, representative)





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





            #VoronoiFuzzyColor.visualize_voronoi(voronoi_volume)
            plt.close('all')


            return voronoi_volume
        else:
            # Handle the case where there are no valid Voronoi regions
            print("No valid Voronoi regions found.")
            return None  # Or you can return an empty volume or handl
        



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