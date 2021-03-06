"""
Module for handling objects composed of cubic bezier curves
"""

from functools import lru_cache
import numpy as np
from typing import Any, List, Tuple, Optional,  Iterable, Iterator

from raytracing.ray import orthogonal, Ray
from raytracing.shade import ShadeRec
from .geometric_object import GeometricObject, hit_aabbox


def englobing_aabbox(aabboxes: List[np.ndarray]) -> np.ndarray:
    """Return a aabbox englobing a list of aabboxes"""
    aabboxes = np.array(aabboxes)
    return np.array([np.min(aabboxes[:, 0, :], axis=0),
                     np.max(aabboxes[:, 1, :], axis=0)])


def cubic_real_roots(a0: float, a1: float, a2: float, a3: float) -> \
                    List[float]:
    """
    Returns the real roots X of a cubic polynomial defined as

    .. math::
        a_0 + a_1 X + a_2 X^2 + a_3 X^3 = 0
    """

    # For more info see wikipedia: cubic equation
    if not np.isclose(a3, 0):
        a, b, c, d = a3, a2, a1, a0
        p = (3*a*c-b**2)/3/a**2
        q = (2*b**3-9*a*b*c+27*a**2*d)/27/a**3
        if np.isclose(p, 0):
            t = [np.cbrt(-q)]
        else:
            discr = -(4*p**3+27*q**2)
            if np.isclose(discr, 0):
                if np.isclose(q, 0):
                    t = [0]
                else:
                    t = [3*q/p, -3*q/2/p]
            elif discr < 0:
                t = [
                    np.cbrt(-q/2+np.sqrt(-discr/108)) +
                    np.cbrt(-q/2-np.sqrt(-discr/108))
                ]
            else:
                t = [2*np.sqrt(-p/3)*np.cos(1/3*np.arccos(3*q/2/p*np.sqrt(
                    -3/p))-2*np.pi*k/3) for k in range(3)]
        roots = [x-b/3/a for x in t]
    elif not np.isclose(a2, 0):
        a, b, c = a2, a1, a0
        discr = b**2 - 4 * a * c
        if discr > 0:
            roots = [
                (-b + np.sqrt(discr))/2/a,
                (-b - np.sqrt(discr))/2/a,
            ]
        elif np.isclose(discr, 0):
            roots = [-b/2/a]
        else:
            roots = []
    elif not np.isclose(a1, 0):
        a, b = a1, a0
        roots = [-b/a]
    else:
        roots = []  # Ignore infinite solutions for 0*x = 0
    return roots


def find_first_hit(ray: Ray, objects: Iterable[Any]) -> ShadeRec:
    result = ShadeRec()
    for obj in objects:
        shade = obj.hit(ray)
        if Ray.min_travel < shade.travel_dist < result.travel_dist:
            result = shade
    return result


class CubicBezier(object):
    """
    Cubic bezier segment defined as

    .. math::
        \\vec{X}(s) = (1-s)^3 \\vec{p_0} + 3 s (1-s)^2 \\vec{p_1}
                      + 3 s^2 (1-s) \\vec{p_2} + s^3 \\vec{p_3}

    for :math:`0 \\le s \\le 1`

    :type points: array_like of size (4,2)
    """

    def __init__(self, points: np.ndarray):
        self._p = np.array(points)

    def __repr__(self) -> str:
        return f"CubicBezier([{self._p[0]}, {self._p[1]}, {self._p[2]}, " \
               f"{self._p[3]}])"

    def eval(self, s):
        p0, p1, p2, p3 = self._p
        return (1-s)**3*p0+3*s*(1-s)**2*p1+3*s**2*(1-s)*p2+s**3*p3

    @property
    def aabbox(self) -> np.ndarray:
        return self._aabbox()

    @lru_cache(maxsize=1)
    def _aabbox(self) -> np.ndarray:
        # The box is slightly larger than the minimal box.
        # It prevents the box to have a zero dimension if the object is a line
        # aligned with vertical or horizontal.
        return np.array([np.min(self._p, axis=0)-1e-6,
                         np.max(self._p, axis=0)+1e-6])

    def tangent(self, s: float) -> np.ndarray:
        """Returns the tangent at the curve at curvilinear coordinate s"""

        p0, p1, p2, p3 = self._p
        diff_1 = -3*(p0-3*p1+3*p2-p3)*s**2 + 6*(p0-2*p1+p2)*s-3*(p0-p1)
        # If the first derivative is not zero, it is parallel to the tangent
        if np.linalg.norm(diff_1) > 1e-8:
            return diff_1/np.linalg.norm(diff_1)
        # but is the first derivative is zero, we need to get the second order
        else:
            diff_2 = -6*(p0-3*p1+3*p2-p3)*s + 6*(p0-2*p1+p2)
            if np.linalg.norm(diff_2) > 1e-8:
                return diff_2 / np.linalg.norm(diff_2)
            else:
                diff_3 = -6*(p0-3*p1+3*p2-p3)
                return diff_3 / np.linalg.norm(diff_3)

    def normal(self, s: float) -> np.ndarray:
        """Returns a vector normal at the curve at curvilinear coordinate s"""

        return orthogonal(self.tangent(s))

    def intersection_beam(self, ray: Ray) -> List[Tuple[float, float]]:
        """
        Returns all couples :math:`(s, t)` such that there exist
        :math:`\\vec{X}` satisfying

        .. math::
            \\vec{X} = (1-s)^3 \\vec{p_0} + 3 s (1-s)^2 \\vec{p_1}
            + 3 s^2 (1-s) \\vec{p_2} + s^3 \\vec{p_3}
        and
        .. math::
            \\vec{X} = \\vec{o} + t \\vec{d}
        with :math:`0 \\lq s \\lq 1` and :math:`t >= 0`
        """

        p0, p1, p2, p3 = self._p
        a = orthogonal(ray.direction)
        a0 = np.dot(a, p0 - ray.origin)
        a1 = -3 * np.dot(a, p0 - p1)
        a2 = 3 * np.dot(a, p0 - 2 * p1 + p2)
        a3 = np.dot(a, -p0 + 3 * p1 - 3 * p2 + p3)
        roots = cubic_real_roots(a0, a1, a2, a3)
        intersection_points = [(1-s)**3*p0 + 3*s*(1-s)**2*p1
                               + 3*s**2*(1-s)*p2 + s**3*p3 for s in roots]
        travel = [np.dot(X-ray.origin, ray.direction) for X in
                  intersection_points]

        def valid_domain(s, t):
            return 0 <= s <= 1 and t > Ray.min_travel

        return [(s, t) for (s, t) in zip(roots, travel) if valid_domain(s, t)]

    def num_hits(self, ray: Ray) -> int:
        if hit_aabbox(ray, self.aabbox):
            return len(self.intersection_beam(ray))
        else:
            return 0

    def hit(self, ray: Ray) -> ShadeRec:
        """
        Returns a shade with the information for the first intersection
        of a beam with the bezier segment
        """

        shade = ShadeRec()  # default no hit
        if hit_aabbox(ray, self.aabbox):
            intersect_params = self.intersection_beam(ray)
            travel_dist = [t for (__, t) in intersect_params]
            if len(travel_dist) > 0:  # otherwise error with np.argmin
                shade.normal = True
                first_hit = np.argmin(travel_dist)
                shade.travel_dist = travel_dist[first_hit]
                shade.local_hit_point = ray.origin + shade.travel_dist * \
                                        ray.direction
                shade.normal = self.normal(intersect_params[first_hit][0])
                shade.set_normal_same_side(ray.origin)
        return shade


class CubicBezierPath(object):
    """Single path composed of a succession of CubicBezier segments"""

    def __init__(self, list_: List[CubicBezier]):
        if len(list_) == 0:
            raise RuntimeError("Can't initialise cubic path from empty list")
        self._bezier_list: List[CubicBezier] = list(list_)

    def __repr__(self) -> str:
        concat_seg = ", ".join(bez.__repr__() for bez in self._bezier_list)
        return f"CubicBezierPath([{concat_seg}])"

    def add_bezier(self, bezier: CubicBezier):
        self._bezier_list.append(bezier)
        self._aabbox.cache_clear()

    def endpoint_info(self) -> Tuple[np.ndarray, np.ndarray]:
        """Returns the location of the end point of the path and its tangent"""
        last_segment = self._bezier_list[-1]  # always at least one element
        return last_segment.eval(1), last_segment.tangent(1)

    @property
    def aabbox(self):
        return self._aabbox()

    @lru_cache(maxsize=1)
    def _aabbox(self) -> np.ndarray:
        """Computes an axis aligned bounding box for the object

        :return: [[x_min, y_min], [x_max, y_max]], an array containing
            the bottom left corner and top right corner of the box
        """

        bezier_aabboxes = [bez.aabbox for bez in self._bezier_list]
        return englobing_aabbox(bezier_aabboxes)

    def hit(self, ray: Ray) -> ShadeRec:
        """
        Returns a shade with the information for the first intersection
        of a beam one of the Bezier segment composing the path
        """

        result = ShadeRec()
        if hit_aabbox(ray, self.aabbox):
            result = find_first_hit(ray, self._bezier_list)
        return result

    def num_hits(self, ray: Ray) -> int:
        if hit_aabbox(ray, self.aabbox):
            return sum([segment.num_hits(ray) for segment in
                        self._bezier_list])
        else:
            return 0


class CompositeCubicBezier(GeometricObject):
    """Set of paths represented by cubic Bezier curves

    :param list_: List of subpaths forming the superpath.
    """

    def __init__(self, list_: Optional[List[CubicBezierPath]] = None):
        if list_ is None:
            list_ = []
        super().__init__()
        self._subpath_list = list(list_)

    def __repr__(self) -> str:
        concat_paths = ", ".join(seg.__repr__() for seg in self._subpath_list)
        return f"CompositeCubicBezier([{concat_paths}])"

    def __iter__(self) -> Iterator[CubicBezierPath]:
        return iter(self._subpath_list)

    def add_subpath(self, subpath: CubicBezierPath):
        self._subpath_list.append(subpath)
        self._aabbox.cache_clear()

    @property
    def aabbox(self) -> np.ndarray:
        return self._aabbox()

    @lru_cache(maxsize=1)
    def _aabbox(self) -> np.ndarray:
        """Computes an axis aligned bounding box for the object

        :return: [[x_min, y_min], [x_max, y_max]], an array containing
            the bottom left corner and top right corner of the box
        """

        subpaths_aabboxes = [sub.aabbox for sub in self._subpath_list]
        return englobing_aabbox(subpaths_aabboxes)

    def hit(self, ray: Ray) -> ShadeRec:
        """
        Returns a shade with the information for the first intersection
        of a beam with one of the subpaths composing the superpath
        """

        result = ShadeRec()
        if hit_aabbox(ray, self.aabbox):
            result = find_first_hit(ray, self._subpath_list)
            result.hit_geometry = self
        return result

    def is_inside(self, ray: Ray) -> bool:
        # A ray is inside an object if it intersect its boundary an odd
        # number of times
        return (self.num_hits(ray) % 2) == 1

    def num_hits(self, ray: Ray) -> int:
        if hit_aabbox(ray, self.aabbox):
            return sum([path.num_hits(ray) for path in
                        self._subpath_list])
        else:
            return 0
