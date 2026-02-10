### my libraries ###
from Source.geometry.Point import Point
from Source.geometry.Face import Face
from Source.geometry.Volume import Volume
from Source.geometry.GeometryTools import GeometryTools
from Source.colorspace.ReferenceDomain import ReferenceDomain
from Source.geometry.Prototype import Prototype

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
    def get_membership_degree(new_color, prototypes, function, pack):
        """
        Faster membership computation for all prototypes for one LAB color.
        Returns normalized non-zero memberships.
        """
        xyz = Point(new_color[0], new_color[1], new_color[2])

        domain_volume = pack["domain_volume"]
        v_protos = pack["v_protos"]
        v_cores  = pack["v_cores"]
        v_supps  = pack["v_supps"]
        rep_ps   = pack["rep_ps"]
        rep_cs   = pack["rep_cs"]
        rep_ss   = pack["rep_ss"]

        result = {}
        total_membership = 0.0

        for i, proto in enumerate(prototypes):
            label = proto.label
            v_supp = v_supps[i]
            v_core = v_cores[i]
            v_proto = v_protos[i]

            rep_p = rep_ps[i]
            rep_c = rep_cs[i]
            rep_s = rep_ss[i]

            if (not v_supp.isInside(xyz)) or v_supp.isInFace(xyz):
                result[label] = 0.0
                continue

            if v_core.isInside(xyz):
                value = 1.0
                result[label] = value
                total_membership += value
                continue

            p_cube = GeometryTools.intersection_with_volume(domain_volume, rep_p, xyz)
            dist_cube = GeometryTools.euclidean_distance(rep_p, p_cube) if p_cube is not None else float('inf')

            p_face = GeometryTools.intersection_with_volume(v_core, rep_c, xyz)
            param_a = GeometryTools.euclidean_distance(rep_c, p_face) if p_face is not None else dist_cube

            p_face = GeometryTools.intersection_with_volume(v_proto, rep_p, xyz)
            param_b = GeometryTools.euclidean_distance(rep_p, p_face) if p_face is not None else dist_cube

            p_face = GeometryTools.intersection_with_volume(v_supp, rep_s, xyz)
            param_c = GeometryTools.euclidean_distance(rep_s, p_face) if p_face is not None else dist_cube

            function.setParam([param_a, param_b, param_c])
            d = GeometryTools.euclidean_distance(rep_p, xyz)
            value = function.getValue(d)

            if value < 0.0:
                value = 0.0
            elif value > 1.0:
                value = 1.0

            result[label] = value
            total_membership += value

        if total_membership == 0.0:
            return {}

        for k in list(result.keys()):
            v = result[k] / total_membership
            if v == 0.0:
                del result[k]
            else:
                result[k] = v

        return result




    @staticmethod
    def get_membership_degree_for_prototype(new_color, prototype, core, support, function):
        """
        Calculate fuzzy membership degree of a LAB color to a single prototype.
        """

        # --- Local references (VERY IMPORTANT for speed) ---
        v_proto = prototype.voronoi_volume
        v_core  = core.voronoi_volume
        v_supp  = support.voronoi_volume

        rep_p = v_proto.getRepresentative()
        rep_c = v_core.getRepresentative()
        rep_s = v_supp.getRepresentative()

        # Create point (assumed LAB)
        xyz = Point(new_color[0], new_color[1], new_color[2])

        # Outside support → 0
        if not v_supp.isInside(xyz) or v_supp.isInFace(xyz):
            return 0.0

        # Inside core → 1
        if v_core.isInside(xyz):
            return 1.0

        # --- Distance to domain cube (fallback) ---
        p_cube = GeometryTools.intersection_with_volume(
            ReferenceDomain.default_voronoi_reference_domain().get_volume(),
            rep_p,
            xyz
        )
        dist_cube = (
            GeometryTools.euclidean_distance(rep_p, p_cube)
            if p_cube is not None else float('inf')
        )

        # --- param a (core boundary) ---
        p_face = GeometryTools.intersection_with_volume(v_core, rep_c, xyz)
        param_a = (
            GeometryTools.euclidean_distance(rep_c, p_face)
            if p_face is not None else dist_cube
        )

        # --- param b (prototype boundary) ---
        p_face = GeometryTools.intersection_with_volume(v_proto, rep_p, xyz)
        param_b = (
            GeometryTools.euclidean_distance(rep_p, p_face)
            if p_face is not None else dist_cube
        )

        # --- param c (support boundary) ---
        p_face = GeometryTools.intersection_with_volume(v_supp, rep_s, xyz)
        param_c = (
            GeometryTools.euclidean_distance(rep_s, p_face)
            if p_face is not None else dist_cube
        )

        # Membership function
        function.setParam([param_a, param_b, param_c])
        d = GeometryTools.euclidean_distance(rep_p, xyz)

        return function.getValue(d)
