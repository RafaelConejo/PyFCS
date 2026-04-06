### my libraries ###
from Source.geometry.Point import Point
from Source.geometry.Plane import Plane
from Source.geometry.Face import Face
from Source.geometry.Volume import Volume
from Source.geometry.GeometryTools import GeometryTools
from Source.colorspace.ReferenceDomain import ReferenceDomain
from Source.geometry.Prototype import Prototype


class FuzzyColor:
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
    def update_geometry(prototypes, cores, supports):
        """
        Java-style adjustment (updateVoronoiFuzzyColors):
        - If a support vertex of c1 falls inside the core of c2, that face is retracted.
        - If a core vertex of c2 falls inside the support of c1, the nearest face is moved.
        """
        n = len(prototypes)

        for i in range(n):
            c1 = prototypes[i]
            s1 = supports[i].voronoi_volume
            rep1 = c1.voronoi_volume.getRepresentative()

            for j in range(n):
                if i == j:
                    continue

                core2 = cores[j].voronoi_volume

                # Rule 1: support(i) vertex inside core(j)
                for fs in s1.getFaces():
                    vi = fs.getArrayVertex()
                    if not vi:
                        continue

                    for v in vi:
                        if core2.isInside(v) and not core2.isInFace(v):
                            p_face = GeometryTools.intersection_with_volume(core2, v, rep1)
                            if p_face is not None:
                                new_plane = Plane.from_normal_point(fs.getPlane().getNormal(), p_face)
                                fs.setPlane(new_plane)

                                # Recalculate vertices
                                if fs.getArrayVertex():
                                    new_vs = []
                                    for vv in fs.getArrayVertex():
                                        nv = GeometryTools.intersection_plane_rect(new_plane, rep1, vv)
                                        if nv is not None:
                                            new_vs.append(nv)
                                    fs.setArrayVertex(new_vs)
                            break

                # Rule 2: core(j) vertex inside support(i)
                for fk in core2.getFaces():
                    vi = fk.getArrayVertex()
                    if not vi:
                        continue

                    for vk in vi:
                        if s1.isInside(vk) and not s1.isInFace(vk):
                            nearest = None
                            min_d = float("inf")

                            for fs in s1.getFaces():
                                d = GeometryTools.distance_point_plane(fs.getPlane(), vk)
                                if d < min_d:
                                    min_d = d
                                    nearest = fs

                            if nearest is not None:
                                new_plane = Plane.from_normal_point(nearest.getPlane().getNormal(), vk)
                                nearest.setPlane(new_plane)

                                if nearest.getArrayVertex():
                                    new_vs = []
                                    for vv in nearest.getArrayVertex():
                                        nv = GeometryTools.intersection_plane_rect(new_plane, rep1, vv)
                                        if nv is not None:
                                            new_vs.append(nv)
                                    nearest.setArrayVertex(new_vs)
                            break








    @staticmethod
    def _raw_membership_for_index(new_color, i, function, pack):
        xyz = Point(new_color[0], new_color[1], new_color[2])

        domain_volume = pack["domain_volume"]
        v_protos = pack["v_protos"]
        v_cores = pack["v_cores"]
        v_supps = pack["v_supps"]
        rep = pack["rep"][i]

        v_supp = v_supps[i]
        v_core = v_cores[i]
        v_proto = v_protos[i]

        if not v_supp.isInside(xyz):
            return 0.0

        if v_core.isInside(xyz):
            return 1.0

        p_cube = GeometryTools.intersection_with_volume(domain_volume, rep, xyz)
        if p_cube is None:
            return 0.0

        p_face = GeometryTools.intersection_with_volume(v_core, rep, xyz)
        if p_face is None:
            return 0.0
        param_a = GeometryTools.euclidean_distance(rep, p_face)

        p_face = GeometryTools.intersection_with_volume(v_proto, rep, xyz)
        if p_face is None:
            return 0.0
        param_b = GeometryTools.euclidean_distance(rep, p_face)

        p_face = GeometryTools.intersection_with_volume(v_supp, rep, xyz)
        if p_face is None:
            return 0.0
        param_c = GeometryTools.euclidean_distance(rep, p_face)

        function.setParam([param_a, param_b, param_c])
        d = GeometryTools.euclidean_distance(rep, xyz)
        value = function.getValue(d)

        if value < 0.0:
            return 0.0
        if value > 1.0:
            return 1.0
        return value

    @staticmethod
    def get_membership_degree_mapping_all(new_color, prototypes, function, pack) -> int:
        xyz = Point(new_color[0], new_color[1], new_color[2])

        v_cores = pack["v_cores"]
        v_supps = pack["v_supps"]

        # Early stop: point inside a core
        for i in range(len(prototypes)):
            if not v_supps[i].isInside(xyz):
                continue
            if v_cores[i].isInside(xyz):
                return i

        best_idx = -1
        best_val = 0.0

        for i in range(len(prototypes)):
            v = FuzzyColor._raw_membership_for_index(new_color, i, function, pack)

            if v > best_val:
                best_val = v
                best_idx = i

        return best_idx if best_val > 0.0 else -1

    @staticmethod
    def get_membership_degree(new_color, prototypes, function, pack):
        xyz = Point(*new_color)

        v_cores = pack["v_cores"]
        v_supps = pack["v_supps"]

        core_hits = []
        for i in range(len(prototypes)):
            if not v_supps[i].isInside(xyz):
                continue
            if v_cores[i].isInside(xyz):
                core_hits.append(i)

        if len(core_hits) == 1:
            return {prototypes[core_hits[0]].label: 1.0}

        if len(core_hits) > 1:
            best_idx = min(
                core_hits,
                key=lambda i: GeometryTools.euclidean_distance(pack["rep"][i], xyz),
            )
            return {prototypes[best_idx].label: 1.0}

        raw = {}
        total = 0.0

        for i in range(len(prototypes)):
            v = FuzzyColor._raw_membership_for_index(new_color, i, function, pack)
            if v > 0.0:
                raw[prototypes[i].label] = v
                total += v

        if not raw:
            return {}

        if len(raw) == 1:
            k = next(iter(raw))
            return {k: 1.0}

        return {k: v / total for k, v in raw.items()}

    @staticmethod
    def get_membership_degree_for_prototype(new_color, prototype, core, support, function):
        """
        Calculate fuzzy membership degree of a LAB color to a single prototype.
        """
        # Local references for better performance
        v_proto = prototype.voronoi_volume
        v_core = core.voronoi_volume
        v_supp = support.voronoi_volume

        rep_p = v_proto.getRepresentative()
        rep_c = v_core.getRepresentative()
        rep_s = v_supp.getRepresentative()

        # Create point (assumed LAB)
        xyz = Point(new_color[0], new_color[1], new_color[2])

        # Outside support -> 0
        if not v_supp.isInside(xyz):
            return 0.0

        # Inside core -> 1
        if v_core.isInside(xyz):
            return 1.0

        # Distance to domain cube (fallback)
        p_cube = GeometryTools.intersection_with_volume(
            ReferenceDomain.default_voronoi_reference_domain().get_volume(),
            rep_p,
            xyz,
        )
        if p_cube is None:
            return 0.0

        p_face = GeometryTools.intersection_with_volume(v_core, rep_c, xyz)
        if p_face is None:
            return 0.0
        param_a = GeometryTools.euclidean_distance(rep_c, p_face)

        p_face = GeometryTools.intersection_with_volume(v_proto, rep_p, xyz)
        if p_face is None:
            return 0.0
        param_b = GeometryTools.euclidean_distance(rep_p, p_face)

        p_face = GeometryTools.intersection_with_volume(v_supp, rep_s, xyz)
        if p_face is None:
            return 0.0
        param_c = GeometryTools.euclidean_distance(rep_s, p_face)

        function.setParam([param_a, param_b, param_c])
        d = GeometryTools.euclidean_distance(rep_p, xyz)

        value = function.getValue(d)
        return max(0.0, min(1.0, value))