### my libraries ###
from PyFCS.geometry.Point import Point
from PyFCS.geometry.GeometryTools import GeometryTools
from PyFCS.geometry.Face import Face
from PyFCS.geometry.Volume import Volume
from PyFCS.geometry.ReferenceDomain import ReferenceDomain
from PyFCS.membership.MembershipFunction import MembershipFunction

class FuzzyColorSpace:
    def __init__(self, space_name, prototypes):
        self.space_name = space_name
        self.prototypes = prototypes
        self.function = MembershipFunction()
        self.lab_reference_domain = ReferenceDomain.default_voronoi_reference_domain()
        
        self.scaling_factor = 0.5

        self.cores, self.supports = self.create_core_support(prototypes)




    def add_face_to_core_support(self, face, representative, core, support):
        # Calculate the distance between the face and the representative point
        dist = GeometryTools.distance_point_plane(face.p, representative) * (1 - self.scaling_factor)
        
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


    def create_core_support(self, prototypes):
        core_volumes = []
        support_volumes = []
        for proto in prototypes:
            core_volume = Volume(Point(*proto.positive))
            support_volume = Volume(Point(*proto.positive))

            for face in proto.voronoi_volume.getFaces():
                    self.add_face_to_core_support(face, Point(*proto.positive), core_volume, support_volume)
            
            core_volumes.append(core_volume)
            support_volumes.append(support_volume)

        return core_volumes, support_volumes








    def calculate_membership(self, new_point):
        result = {}
        total_membership = 0
        new_point = Point(new_point[0], new_point[1], new_point[2])
        for proto, prototype in enumerate(self.prototypes):
            label = prototype.label
            if not isinstance(new_point, Point):
                new_point = self.lab_reference_domain.transform(Point(new_point.x, new_point.y, new_point.z))

            xyz = new_point

            if self.supports[proto].isInside(xyz) and not self.supports[proto].isInFace(xyz):
                if self.cores[proto].isInside(xyz):
                    value = 1
                    result[label] = value
                else:
                    dist_cube = float('inf')
                    p_cube = GeometryTools.intersection_with_volume(self.lab_reference_domain.get_volume(), prototype.voronoi_volume.getRepresentative(), xyz)
                    if p_cube is not None:
                        dist_cube = GeometryTools.euclidean_distance(prototype.voronoi_volume.getRepresentative(), p_cube)
                    else:
                        print("No intersection with cube")

                    dist_face = float('inf')
                    p_face = GeometryTools.intersection_with_volume(self.cores[proto], self.cores[proto].getRepresentative(), xyz)
                    if p_face is not None:
                        dist_face = GeometryTools.euclidean_distance(self.cores[proto].getRepresentative(), p_face)
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
                    p_face = GeometryTools.intersection_with_volume(self.supports[proto], self.supports[proto].getRepresentative(), xyz)
                    if p_face is not None:
                        dist_face = GeometryTools.euclidean_distance(self.supports[proto].getRepresentative(), p_face)
                    else:
                        dist_face = dist_cube
                    param_c = dist_face

                    self.function.setParam([param_a, param_b, param_c])
                    value = self.function.getValue(GeometryTools.euclidean_distance(prototype.voronoi_volume.getRepresentative(), xyz))

                    if value == 0 or value == 1:
                        print("Error membership value with point [{},{},{}] in support. Value must be (0,1)".format(xyz.x, xyz.y, xyz.z))

                    result[label] = value

                total_membership += value

            else:
                result[label] = 0

        for label, value in result.items():
            result[label] /= total_membership
        return result
