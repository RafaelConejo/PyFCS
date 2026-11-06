### my libraries ###
from Source.geometry.Point import Point
from Source.geometry.Plane import Plane
from Source.geometry.Face import Face
from Source.geometry.Volume import Volume
from Source.geometry.GeometryTools import GeometryTools
from Source.geometry.Prototype import Prototype
from Source.membership.MembershipFunction import MembershipFunction


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
        f1 = Face(p=parallel_planes[0], infinity=face.infinity, source_index=face.source_index)
        f2 = Face(p=parallel_planes[1], infinity=face.infinity, source_index=face.source_index)

        if face.getArrayVertex() is not None:
            for v in face.getArrayVertex():
                vertex_f1 = GeometryTools.intersection_plane_rect(f1.p, representative, v)
                vertex_f2 = GeometryTools.intersection_plane_rect(f2.p, representative, v)

                if vertex_f1 is not None:
                    f1.addVertex(vertex_f1)
                if vertex_f2 is not None:
                    f2.addVertex(vertex_f2)

        # Add the corresponding face to core and support
        if GeometryTools.distance_point_plane(f1.p, representative) < GeometryTools.distance_point_plane(f2.p, representative):
            core.addFace(f1)
            support.addFace(f2)
        else:
            core.addFace(f2)
            support.addFace(f1)


    @staticmethod
    def create_core_support(prototypes, scaling_factor=0.5, lambda1=None, lambda2=None):
        """
        Create core and support volumes by scaling the prototypes according to the scaling factor.

        Parameters:
            prototypes (list): List of Prototype objects.
            scaling_factor (float): The scaling factor.

        Returns:
            tuple: A tuple containing the core volumes and support volumes.
        """
        if lambda1 is None:
            lambda1 = float(scaling_factor)
        if lambda2 is None:
            lambda2 = 2.0 - float(scaling_factor)
        if not (0.0 <= lambda1 < 1.0 and 1.0 < lambda2 <= 2.0):
            raise ValueError("Require 0 <= lambda1 < 1 and 1 < lambda2 <= 2.")

        # Historical partition 0.5 / 1.5 uses EXACTLY its previous calculation.
        keep_legacy = abs(lambda1 - 0.5) < 1e-12 and abs(lambda2 - 1.5) < 1e-12

        def scaled_face(face, center, scale):
            pl = face.getPlane()
            dot = pl.A * center.x + pl.B * center.y + pl.C * center.z
            scaled_plane = Plane(pl.A, pl.B, pl.C, scale * pl.D + (scale - 1) * dot)
            vertices = face.getArrayVertex()
            points = None
            if vertices is not None:
                points = [Point(center.x + scale * (v.x - center.x),
                                center.y + scale * (v.y - center.y),
                                center.z + scale * (v.z - center.z)) for v in vertices]
            return Face(p=scaled_plane, vertex=points, infinity=face.infinity,
                        source_index=face.source_index,
                        is_domain_boundary=face.is_domain_boundary)

        core_volumes = []
        support_volumes = []
        for proto in prototypes:
            core_volume = Volume(Point(*proto.positive))
            support_volume = Volume(Point(*proto.positive))

            for face in proto.voronoi_volume.getFaces():
                if face.isDomainBoundary():
                    # This is a viewing/domain constraint, not a fuzzy color
                    # transition.  Keep its plane at the actual domain edge
                    # in both volumes; membership rays ignore it entirely.
                    core_volume.addFace(face.copy())
                    support_volume.addFace(face.copy())
                    continue
                if keep_legacy:
                    FuzzyColor.add_face_to_core_support(face, Point(*proto.positive), core_volume, support_volume, scaling_factor)
                else:
                    core_volume.addFace(scaled_face(face, Point(*proto.positive), lambda1))
                    support_volume.addFace(scaled_face(face, Point(*proto.positive), lambda2))

            core_volume_dict = Prototype(
                label=proto.label,
                positive=proto.positive,
                voronoi_volume=core_volume,
            )
            support_volume_dict = Prototype(
                label=proto.label,
                positive=proto.positive,
                voronoi_volume=support_volume,
            )
            
            core_volumes.append(core_volume_dict)
            support_volumes.append(support_volume_dict)

        return core_volumes, support_volumes


    @staticmethod
    def update_geometry(prototypes, cores, supports, reference_domain=None, eps=1e-7):
        """JFCS-style support repair for disjoint atomic fuzzy colors.

        JFCS moves a support plane inward if a support vertex enters another
        color's core, or if another core vertex enters this support.  Domain
        clipping planes are *not* color boundaries and must never be moved.
        Only conflicts witnessed inside the declared model domain are repaired.

        This deliberately does not alter the cores or Voronoi bisectors.  It
        returns the number of adjusted support faces for regression tests and
        diagnostic use.  The caller must not use it on non-disjoint spaces or
        imported FCS volumes, because that changes the intended semantics.
        """
        from math import isfinite

        def inside_domain(vertex):
            return (reference_domain is None or
                    reference_domain.contains_coordinates(
                        (vertex.x, vertex.y, vertex.z), eps=eps))

        def strictly_inside(volume, vertex):
            if not volume.isInside(vertex, eps=eps):
                return False
            # Ignore rendering-only domain faces when detecting contact.
            return not any(
                abs(f.getPlane().evaluatePoint(vertex)) <= eps
                for f in volume.getFaces() if not f.isDomainBoundary()
            )

        def retract(face, origin, through):
            """Move a real support face inward; refuse unstable corrections."""
            if face.isDomainBoundary():
                return False
            old_plane = face.getPlane()
            normal = old_plane.getNormal()
            new_plane = Plane.from_normal_point(normal, through)
            modulus = (normal.a ** 2 + normal.b ** 2 + normal.c ** 2) ** 0.5
            if modulus <= eps:
                return False
            old_signed = abs(old_plane.evaluatePoint(origin)) / modulus
            new_signed = abs(new_plane.evaluatePoint(origin)) / modulus
            # The support is allowed to SHRINK, never expand or cross its seed.
            if new_signed <= eps or new_signed >= old_signed - eps:
                return False
            if old_plane.evaluatePoint(origin) * new_plane.evaluatePoint(origin) <= 0:
                return False
            vertices = face.getArrayVertex()
            if vertices:
                new_vertices = []
                for v in vertices:
                    q = GeometryTools.intersection_plane_rect(new_plane, origin, v)
                    if q is None or not all(isfinite(x) for x in (q.x, q.y, q.z)):
                        return False
                    new_vertices.append(q)
                face.setArrayVertex(new_vertices)
            face.setPlane(new_plane)
            return True

        # Fast conservative rejection of vertex sets against the target volume.
        # A pair is rejected only when every candidate fails at least one
        # non-degenerate half-space. Potential conflicts retain the original
        # point-by-point tests and support-plane retraction rules.
        import numpy as np

        bounds = (np.asarray(reference_domain.bounds, dtype=float).reshape(3, 2)
                  if reference_domain is not None else None)

        def eligible_vertices(faces):
            values = [(v.x, v.y, v.z)
                      for face in faces for v in (face.getArrayVertex() or ())]
            if not values:
                return np.empty((0, 3), dtype=float)
            coords = np.asarray(values, dtype=float)
            if bounds is not None:
                inside = np.all(
                    (coords >= bounds[:, 0] - eps) &
                    (coords <= bounds[:, 1] + eps), axis=1)
                coords = coords[inside]
            return coords

        def oriented_halfspaces(volume):
            rep = volume.getRepresentative()
            coefficients = []
            for face in volume.getFaces():
                plane = face.getPlane()
                side = plane.evaluatePoint(rep)
                # Volume.isInside() uses a vertex-based fallback in this case.
                # Skipping such a plane is conservative: it cannot reject an
                # otherwise valid candidate.
                if abs(side) <= eps:
                    continue
                coefficients.append((plane.A * side, plane.B * side,
                                     plane.C * side, plane.D * side))
            return np.asarray(coefficients, dtype=float).reshape(-1, 4)

        def may_contain_vertex(coordinates, halfspaces):
            if not len(coordinates):
                return False
            if not len(halfspaces):
                return True
            # A small numerical margin avoids discarding points very close to
            # a separating plane. False positives are checked by the exact
            # Volume.isInside() implementation below.
            signed = (coordinates @ halfspaces[:, :3].T
                      + halfspaces[:, 3])
            return bool(np.any(np.all(signed >= -eps - 1e-8, axis=1)))

        core_data = []
        for entry in cores:
            volume = entry.voronoi_volume
            real_faces = [face for face in volume.getFaces()
                          if not face.isDomainBoundary()]
            core_data.append((volume, real_faces,
                              eligible_vertices(real_faces),
                              oriented_halfspaces(volume)))

        moved = 0
        n = len(prototypes)
        for i in range(n):
            support_i = supports[i].voronoi_volume
            origin = support_i.getRepresentative()
            mutable_faces = [f for f in support_i.getFaces()
                             if not f.isDomainBoundary()]
            support_vertices = eligible_vertices(mutable_faces)
            support_planes = oriented_halfspaces(support_i)

            for j in range(n):
                if i == j:
                    continue
                core_j, core_faces, core_vertices, core_planes = core_data[j]

                # Rule 1: a support vertex is strictly inside the other core.
                if may_contain_vertex(support_vertices, core_planes):
                    for face in mutable_faces:
                        for vertex in face.getArrayVertex() or ():
                            if not inside_domain(vertex) or not strictly_inside(core_j, vertex):
                                continue
                            crossing = GeometryTools.intersection_with_volume(
                                core_j, vertex, origin,
                                ignore_domain_boundaries=True)
                            if crossing is not None and retract(face, origin, crossing):
                                moved += 1
                                # Later tests must see the updated face geometry.
                                support_vertices = eligible_vertices(mutable_faces)
                                support_planes = oriented_halfspaces(support_i)
                                break

                # Rule 2: a core vertex is strictly inside this support.
                if may_contain_vertex(core_vertices, support_planes):
                    for core_face in core_faces:
                        for vertex in core_face.getArrayVertex() or ():
                            if not inside_domain(vertex) or not strictly_inside(support_i, vertex):
                                continue
                            if not mutable_faces:
                                continue
                            nearest = min(
                                mutable_faces,
                                key=lambda f: GeometryTools.distance_point_plane(
                                    f.getPlane(), vertex))
                            if retract(nearest, origin, vertex):
                                moved += 1
                                support_vertices = eligible_vertices(mutable_faces)
                                support_planes = oriented_halfspaces(support_i)
                                break
        return moved


    @staticmethod
    def _raw_membership_for_index(new_color, i, pack):
        xyz = Point(new_color[0], new_color[1], new_color[2])

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

        # The FCS public API already checks the reference domain.  For points
        # inside it, the ray from an in-domain representative necessarily
        # intersects the bounding box. Computing that intersection here was
        # redundant and expensive in pixel-wise mapping; its coordinates were
        # not used by the membership function.

        p_face = GeometryTools.intersection_with_volume(v_core, rep, xyz, ignore_domain_boundaries=True)
        if p_face is None:
            return 0.0
        param_a = GeometryTools.euclidean_distance(rep, p_face)

        p_face = GeometryTools.intersection_with_volume(v_proto, rep, xyz, ignore_domain_boundaries=True)
        if p_face is None:
            return 0.0
        param_b = GeometryTools.euclidean_distance(rep, p_face)

        p_face = GeometryTools.intersection_with_volume(v_supp, rep, xyz, ignore_domain_boundaries=True)
        if p_face is None:
            return 0.0
        param_c = GeometryTools.euclidean_distance(rep, p_face)

        d = GeometryTools.euclidean_distance(rep, xyz)
        value = MembershipFunction.evaluate(d, param_a, param_b, param_c)

        if value < 0.0:
            return 0.0
        if value > 1.0:
            return 1.0
        return value

    @staticmethod
    def get_membership_degree_mapping_all(new_color, prototypes, pack) -> int:
        xyz = Point(new_color[0], new_color[1], new_color[2])

        v_cores = pack["v_cores"]
        v_supps = pack["v_supps"]

        # The first core is not necessarily the nearest: non-disjoint spaces
        # may contain multiple overlapping cores. Use the same deterministic
        # nearest-representative tie-break as get_membership_degree().
        core_hits = []
        for i in range(len(prototypes)):
            if v_supps[i].isInside(xyz) and v_cores[i].isInside(xyz):
                core_hits.append(i)
        if len(core_hits) == 1:
            return core_hits[0]
        if core_hits:
            return min(core_hits,
                       key=lambda i: GeometryTools.euclidean_distance(pack["rep"][i], xyz))

        best_idx = -1
        best_val = 0.0

        for i in range(len(prototypes)):
            v = FuzzyColor._raw_membership_for_index(new_color, i, pack)

            if v > best_val:
                best_val = v
                best_idx = i

        return best_idx if best_val > 0.0 else -1

    @staticmethod
    def get_membership_degree(new_color, prototypes, pack):
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
            v = FuzzyColor._raw_membership_for_index(new_color, i, pack)
            if v > 0.0:
                raw[prototypes[i].label] = v
                total += v

        if not raw:
            # An empty result cannot be normalized. The caller can inspect the
            # original memberships when diagnosing a gap in a partition.
            return {}

        # A partition is presented as a Ruspini distribution (sum(mu) = 1),
        # while calculate_raw_memberships() retains the geometric values for
        # comparisons with JFCS. Avoid modifying already normalized values.
        if abs(total - 1.0) <= 1e-9:
            return raw

        return {k: v / total for k, v in raw.items()}

    @staticmethod
    def get_membership_degree_for_prototype(new_color, prototype, core, support):
        """
        Calculate the raw membership of a model-space point in one prototype.

        The public FuzzyColorSpace API validates the model reference domain.
        This geometry-only helper must not assume the legacy LAB box when
        used with an RGB prototype.
        """
        # Local references for better performance
        v_proto = prototype.voronoi_volume
        v_core = core.voronoi_volume
        v_supp = support.voronoi_volume

        rep_p = v_proto.getRepresentative()
        rep_c = v_core.getRepresentative()
        rep_s = v_supp.getRepresentative()

        # Coordinates are already in the prototype's geometric model.
        xyz = Point(new_color[0], new_color[1], new_color[2])

        # Outside support -> 0
        if not v_supp.isInside(xyz):
            return 0.0

        # Inside core -> 1
        if v_core.isInside(xyz):
            return 1.0

        p_face = GeometryTools.intersection_with_volume(v_core, rep_c, xyz, ignore_domain_boundaries=True)
        if p_face is None:
            return 0.0
        param_a = GeometryTools.euclidean_distance(rep_c, p_face)

        p_face = GeometryTools.intersection_with_volume(v_proto, rep_p, xyz, ignore_domain_boundaries=True)
        if p_face is None:
            return 0.0
        param_b = GeometryTools.euclidean_distance(rep_p, p_face)

        p_face = GeometryTools.intersection_with_volume(v_supp, rep_s, xyz, ignore_domain_boundaries=True)
        if p_face is None:
            return 0.0
        param_c = GeometryTools.euclidean_distance(rep_s, p_face)

        d = GeometryTools.euclidean_distance(rep_p, xyz)
        value = MembershipFunction.evaluate(d, param_a, param_b, param_c)
        return max(0.0, min(1.0, value))