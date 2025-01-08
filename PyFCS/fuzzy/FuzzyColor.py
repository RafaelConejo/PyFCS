### my libraries ###
from PyFCS.geometry.Point import Point
from PyFCS.geometry.Face import Face
from PyFCS.geometry.Volume import Volume
from PyFCS.geometry.GeometryTools import GeometryTools
from PyFCS.colorspace.ReferenceDomain import ReferenceDomain
from PyFCS import Prototype

class FuzzyColor():
    @staticmethod
    def add_face_to_core_support(face, representative, core, support, scaling_factor):
        """
        Add faces to the core and support volumes by scaling the prototypes according to the scaling factor.

        Parameters:
            face (Face): The face to be scaled.
            representative (Point): The representative point of the face.
            core (Volume): The core volume.
            support (Volume): The support volume.
            scaling_factor (float): The scaling factor.

        Returns:
            None
        """
        # Calculate the distance between the face and the representative point
        dist = GeometryTools.distance_point_plane(face.p, representative) * (1 - scaling_factor)
        
        # Create parallel planes for core and support
        parallel_planes = GeometryTools.parallel_planes(face.p, dist)
        f1 = Face(p=parallel_planes[0], infinity=face.infinity)
        f2 = Face(p=parallel_planes[1], infinity=face.infinity)

        if face.getArrayVertex() is not None:
            # Create new vertices for each face of the core and support
            for v in face.getArrayVertex():
                vertex_f1 = GeometryTools.intersection_plane_rect(f1.p, representative, Point(v[0], v[1], v[2]))
                vertex_f2 = GeometryTools.intersection_plane_rect(f2.p, representative, Point(v[0], v[1], v[2]))
                f1.addVertex(vertex_f1)
                f2.addVertex(vertex_f2)

        # Add the corresponding face to core and support
        if GeometryTools.distance_point_plane(f1.p, representative) < GeometryTools.distance_point_plane(f2.p, representative):
            core.addFace(f1)
            support.addFace(f2)
        else:
            core.addFace(f2)
            support.addFace(f1)


    @staticmethod
    def create_core_support(prototypes, scaling_factor):
        """
        Create core and support volumes by scaling the prototypes according to the scaling factor.

        Parameters:
            prototypes (list): List of Prototype objects.
            scaling_factor (float): The scaling factor.

        Returns:
            tuple: A tuple containing the core volumes and support volumes.
        """
        core_volumes = []
        support_volumes = []
        for proto in prototypes:
            core_volume = Volume(Point(*proto.positive))
            support_volume = Volume(Point(*proto.positive))

            for face in proto.voronoi_volume.getFaces():
                    FuzzyColor.add_face_to_core_support(face, Point(*proto.positive), core_volume, support_volume, scaling_factor)

            core_volume_dict = Prototype(label=proto.label, positive=proto.positive, negatives=proto.negatives, voronoi_volume=core_volume, add_false=proto.add_false)
            support_volume_dict = Prototype(label=proto.label, positive=proto.positive, negatives=proto.negatives, voronoi_volume=support_volume, add_false=proto.add_false)
            
            core_volumes.append(core_volume_dict)
            support_volumes.append(support_volume_dict)

        return core_volumes, support_volumes
    



    @staticmethod
    def get_membership_degree(new_color, prototypes, cores, supports, function):
        """
        Calculate the membership degree of a new color using a membership calculation function and different volumes.

        Parameters:
            new_color (tuple): The new color as a tuple (R, G, B).
            prototypes (list): List of Prototype objects.
            cores (list): List of core volumes.
            supports (list): List of support volumes.
            function (MembershipFunction): The membership calculation function.

        Returns:
            dict: A dictionary containing the membership degree of the new color for each prototype.
        """
        result = {}
        total_membership = 0
        new_color = Point(new_color[0], new_color[1], new_color[2])
        lab_reference_domain = ReferenceDomain.default_voronoi_reference_domain()
        for proto, prototype in enumerate(prototypes):
            label = prototype.label
            if not isinstance(new_color, Point):
                new_color = lab_reference_domain.transform(Point(new_color.x, new_color.y, new_color.z))

            xyz = new_color

            if supports[proto].voronoi_volume.isInside(xyz) and not supports[proto].voronoi_volume.isInFace(xyz):
                if cores[proto].voronoi_volume.isInside(xyz):
                    value = 1
                    result[label] = value
                else:
                    dist_cube = float('inf')
                    p_cube = GeometryTools.intersection_with_volume(lab_reference_domain.get_volume(), prototype.voronoi_volume.getRepresentative(), xyz)
                    if p_cube is not None:
                        dist_cube = GeometryTools.euclidean_distance(prototype.voronoi_volume.getRepresentative(), p_cube)
                    else:
                        print("No intersection with cube")

                    dist_face = float('inf')
                    p_face = GeometryTools.intersection_with_volume(cores[proto].voronoi_volume, cores[proto].voronoi_volume.getRepresentative(), xyz)
                    if p_face is not None:
                        dist_face = GeometryTools.euclidean_distance(cores[proto].voronoi_volume.getRepresentative(), p_face)
                    else:
                        dist_face = dist_cube
                    param_a = dist_face

                    dist_face = float('inf')
                    p_face = GeometryTools.intersection_with_volume(prototype.voronoi_volume, prototype.voronoi_volume.getRepresentative(), xyz)
                    if p_face is not None:
                        dist_face = GeometryTools.euclidean_distance(prototype.voronoi_volume.getRepresentative(), p_face)
                    else:
                        dist_face = dist_cube
                    param_b = dist_face

                    dist_face = float('inf')
                    p_face = GeometryTools.intersection_with_volume(supports[proto].voronoi_volume, supports[proto].voronoi_volume.getRepresentative(), xyz)
                    if p_face is not None:
                        dist_face = GeometryTools.euclidean_distance(supports[proto].voronoi_volume.getRepresentative(), p_face)
                    else:
                        dist_face = dist_cube
                    param_c = dist_face

                    function.setParam([param_a, param_b, param_c])
                    value = function.getValue(GeometryTools.euclidean_distance(prototype.voronoi_volume.getRepresentative(), xyz))

                    if value == 0 or value == 1:
                        print("Error membership value with point [{},{},{}] in support. Value must be (0,1)".format(xyz.x, xyz.y, xyz.z))

                    result[label] = value

                total_membership += value

            else:
                result[label] = 0

        for label, value in result.items():
            result[label] /= total_membership if total_membership != 0 else 1
        return {k: v for k, v in result.items() if v != 0}



    @staticmethod
    def get_membership_degree_for_prototype(new_color, prototype, core, support, function):
        """
        Calculate the membership degree of a new color to a single prototype using a membership calculation function.

        Parameters:
            new_color (tuple): The new color as a tuple (R, G, B).
            prototype (Prototype): The Prototype object.
            core (Volume): The core volume of the prototype.
            support (Volume): The support volume of the prototype.
            function (MembershipFunction): The membership calculation function.

        Returns:
            float: The membership degree of the new color to the prototype.
        """
        result = 0
        new_color = Point(new_color[0], new_color[1], new_color[2])
        lab_reference_domain = ReferenceDomain.default_voronoi_reference_domain()

        if not isinstance(new_color, Point):
            new_color = lab_reference_domain.transform(Point(new_color.x, new_color.y, new_color.z))

        xyz = new_color

        if support.voronoi_volume.isInside(xyz) and not support.voronoi_volume.isInFace(xyz):
            if core.voronoi_volume.isInside(xyz):
                value = 1
                result = value
            else:
                dist_cube = float('inf')
                p_cube = GeometryTools.intersection_with_volume(lab_reference_domain.get_volume(), prototype.voronoi_volume.getRepresentative(), xyz)
                if p_cube is not None:
                    dist_cube = GeometryTools.euclidean_distance(prototype.voronoi_volume.getRepresentative(), p_cube)
                else:
                    print("No intersection with cube")

                dist_face = float('inf')
                p_face = GeometryTools.intersection_with_volume(core.voronoi_volume, core.voronoi_volume.getRepresentative(), xyz)
                if p_face is not None:
                    dist_face = GeometryTools.euclidean_distance(core.voronoi_volume.getRepresentative(), p_face)
                else:
                    dist_face = dist_cube
                param_a = dist_face

                dist_face = float('inf')
                p_face = GeometryTools.intersection_with_volume(prototype.voronoi_volume, prototype.voronoi_volume.getRepresentative(), xyz)
                if p_face is not None:
                    dist_face = GeometryTools.euclidean_distance(prototype.voronoi_volume.getRepresentative(), p_face)
                else:
                    dist_face = dist_cube
                param_b = dist_face

                dist_face = float('inf')
                p_face = GeometryTools.intersection_with_volume(support.voronoi_volume, support.voronoi_volume.getRepresentative(), xyz)
                if p_face is not None:
                    dist_face = GeometryTools.euclidean_distance(support.voronoi_volume.getRepresentative(), p_face)
                else:
                    dist_face = dist_cube
                param_c = dist_face

                function.setParam([param_a, param_b, param_c])
                value = function.getValue(GeometryTools.euclidean_distance(prototype.voronoi_volume.getRepresentative(), xyz))

                if value == 0 or value == 1:
                    print("Error membership value with point [{},{},{}] in support. Value must be (0,1)".format(xyz.x, xyz.y, xyz.z))

                result = value
        else:
            result = 0

        return result