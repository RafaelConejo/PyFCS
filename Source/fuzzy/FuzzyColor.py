### my libraries ###
from Source.geometry.Point import Point
from Source.geometry.Plane import Plane
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
                vertex_f1 = GeometryTools.intersection_plane_rect(f1.p, representative, v)
                vertex_f2 = GeometryTools.intersection_plane_rect(f2.p, representative, v)
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
        Ajuste tipo Java (updateVoronoiFuzzyColors):
        - Si un vértice de support de c1 cae dentro del core de c2, se retrae esa cara.
        - Si un vértice de core de c2 cae dentro del support de c1, se mueve la cara más cercana.
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

                # --- Regla 1: vértice de support(i) dentro de core(j)
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

                                # Recalcular vértices
                                if fs.getArrayVertex():
                                    new_vs = []
                                    for vv in fs.getArrayVertex():
                                        nv = GeometryTools.intersection_plane_rect(new_plane, rep1, vv)
                                        if nv is not None:
                                            new_vs.append(nv)
                                    fs.setArrayVertex(new_vs)
                            break  # mover una vez es suficiente

                # --- Regla 2: vértice de core(j) dentro de support(i)
                for fk in core2.getFaces():
                    vi = fk.getArrayVertex()
                    if not vi:
                        continue

                    for vk in vi:
                        if s1.isInside(vk) and not s1.isInFace(vk):
                            # encontrar cara de support(i) más cercana a vk
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
        v_cores  = pack["v_cores"]
        v_supps  = pack["v_supps"]
        rep   = pack["rep"]

        v_supp = v_supps[i]
        v_core = v_cores[i]
        v_proto = v_protos[i]

        rep = rep[i]

        if (not v_supp.isInside(xyz)) or v_supp.isInFace(xyz):
            return 0.0

        if v_core.isInside(xyz) and not v_core.isInFace(xyz):
            return 1.0

        p_cube = GeometryTools.intersection_with_volume(domain_volume, rep, xyz)
        dist_cube = GeometryTools.euclidean_distance(rep, p_cube) if p_cube is not None else float('inf')

        p_face = GeometryTools.intersection_with_volume(v_core, rep, xyz)
        param_a = GeometryTools.euclidean_distance(rep, p_face) if p_face is not None else dist_cube

        p_face = GeometryTools.intersection_with_volume(v_proto, rep, xyz)
        param_b = GeometryTools.euclidean_distance(rep, p_face) if p_face is not None else dist_cube

        p_face = GeometryTools.intersection_with_volume(v_supp, rep, xyz)
        param_c = GeometryTools.euclidean_distance(rep, p_face) if p_face is not None else dist_cube

        function.setParam([param_a, param_b, param_c])
        d = GeometryTools.euclidean_distance(rep, xyz)
        value = function.getValue(d)

        if value < 0.0:
            return 0.0
        if value > 1.0:
            return 1.0
        return value



    @staticmethod
    def get_best_prototype_index(new_color, prototypes, function, pack) -> int:
        xyz = Point(new_color[0], new_color[1], new_color[2])

        v_cores = pack["v_cores"]
        v_supps = pack["v_supps"]

        # Early stop: core
        for i in range(len(prototypes)):
            if (not v_supps[i].isInside(xyz)) or v_supps[i].isInFace(xyz):
                continue
            if v_cores[i].isInside(xyz) and not v_cores[i].isInFace(xyz):
                print(f"[DEBUG CORE] idx={i} label={prototypes[i].label} -> 1.0")
                return i

        best_idx = -1
        best_val = 0.0

        total = 0.0
        count = 0

        # Para debug detallado
        debug_vals = []

        for i in range(len(prototypes)):
            v = FuzzyColor._raw_membership_for_index(new_color, i, function, pack)

            if v > 0.0:
                total += v
                count += 1
                debug_vals.append((prototypes[i].label, v))

            if v > best_val:
                best_val = v
                best_idx = i

        # DEBUG compacto
        print(f"[DEBUG] sum_raw={total:.4f} | best={best_val:.4f} ({prototypes[best_idx].label if best_idx!=-1 else 'None'}) | count={count}")

        # DEBUG detallado (opcional, puedes comentar si molesta)
        if count > 1:
            print("   ->", ", ".join([f"{lbl}:{val:.3f}" for lbl, val in debug_vals]))

        return best_idx if best_val > 0.0 else -1



    @staticmethod
    def get_membership_degree(new_color, prototypes, function, pack):
        best_idx = FuzzyColor.get_best_prototype_index(new_color, prototypes, function, pack)
        if best_idx == -1:
            return {}

        raw = {}
        total = 0.0

        for i in range(len(prototypes)):
            v = FuzzyColor._raw_membership_for_index(new_color, i, function, pack)
            if v > 0.0:
                raw[prototypes[i].label] = v
                total += v

        if not raw:
            return {prototypes[best_idx].label: 1.0}

        if len(raw) == 1:
            k = next(iter(raw))
            return {k: 1.0}

        if total <= 0.0:
            return {prototypes[best_idx].label: 1.0}

        return {k: v / total for k, v in raw.items()}




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
        if v_core.isInside(xyz) and not v_core.isInFace(xyz):
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
