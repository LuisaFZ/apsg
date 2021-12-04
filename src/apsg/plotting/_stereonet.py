# -*- coding: utf-8 -*-

import sys
import warnings
import pickle

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.cbook as mcb
import matplotlib.animation as animation
from matplotlib.patches import Circle
from scipy.stats import vonmises

try:
    import mplstereonet
except ImportError:
    pass

from apsg.config import apsg_conf
from apsg.helpers._math import sind, cosd, tand, acosd, asind, atand, atan2d, sqrt2
from apsg.math._vector import Vector3, Axial3
from apsg.math._matrix import Matrix3
from apsg.feature._geodata import Lineation, Foliation, Pair, Fault
from apsg.feature._container import (
    FeatureSet,
    Vector3Set,
    LineationSet,
    FoliationSet,
    PairSet,
    FaultSet,
)
from apsg.plotting._stereogrid import StereoGrid
from apsg.feature._tensor import DefGrad3, VelGrad3, Stress3, Ellipsoid, Ortensor3
from apsg.plotting._projection import EqualAreaProj, EqualAngleProj

__all__ = ["StereoNet", "VollmerPlot", "RamsayPlot", "FlinnPlot", "HsuPlot", "RosePlot"]


# Ignore `matplotlib`s deprecation warnings.
warnings.filterwarnings("ignore", category=mcb.mplDeprecation)


"""
settings dict
    - property: value

data dict
    id: obj.tojson()


artists (array of dicts)

    - linear
        - id
        - args
        - kwargs

    - pole
        - id
        - args
        - kwargs

    - great_circle
        - id
        - args
        - kwargs
  """


class StereoNet:
    """
    Blasklas

    Args:
        hemisphere: which hemisphere Default 'lower'
        rotate_data: whether data should be rotated with overlay Default False
        grid_position: orientation of overlay given as ``Pair`` Default pair(0, 0, 0, 0)
        clip_pole: Default 20)
        gridstep: grid step Default 15
        resolution: number of grid lines points Default 361
        n: number of contouring grid points Default 2000
        grid_type: type of contouring grid 'gss' or 'sfs'. Default 'gss'
    """

    def __init__(self, **kwargs):
        self.grid = kwargs.get("grid", True)
        self.show_warnings = kwargs.get("show_warnings", True)
        kind = str(kwargs.get("kind", "Equal-area")).lower()
        if kind in ["equal-area", "schmidt", "earea"]:
            self.proj = EqualAreaProj(**kwargs)
        elif kind in ["equal-angle", "wulff", "eangle"]:
            self.proj = EqualAngleProj(**kwargs)
        else:
            raise TypeError("Only 'Equal-area' and 'Equal-angle' implemented")
        self.angles_gc = np.linspace(
            -90 + 1e-7, 90 - 1e-7, int(self.proj.resolution / 2)
        )
        self.angles_sc = np.linspace(-180 + 1e-7, 180 - 1e-7, self.proj.resolution)
        self.stereogrid = StereoGrid(**kwargs)
        self._kwargs = kwargs
        self._data = {}
        self._artists = []

    def clear(self):
        self._data.clear()
        self._artists = []

    # just for testing
    def __draw_net(self):
        self.fig, self.ax = plt.subplots()
        self.ax.set_aspect(1)
        self.ax.set_axis_off()

        # overlay
        if self.grid:
            ov = self.proj.get_grid_overlay()
            for dip, d in ov["lat_e"].items():
                self.ax.plot(d["x"], d["y"], "k:", lw=1)
            for dip, d in ov["lat_w"].items():
                self.ax.plot(d["x"], d["y"], "k:", lw=1)
            for dip, d in ov["lon_n"].items():
                self.ax.plot(d["x"], d["y"], "k:", lw=1)
            for dip, d in ov["lon_s"].items():
                self.ax.plot(d["x"], d["y"], "k:", lw=1)
            if ov["polehole_n"]:
                self.ax.plot(ov["polehole_n"]["x"], ov["polehole_n"]["y"], "k", lw=1)
            if ov["polehole_s"]:
                self.ax.plot(ov["polehole_s"]["x"], ov["polehole_s"]["y"], "k", lw=1)
            if ov["main_ns"]:
                self.ax.plot(ov["main_ns"]["x"], ov["main_ns"]["y"], "k", lw=1)
            if ov["main_ew"]:
                self.ax.plot(ov["main_ew"]["x"], ov["main_ew"]["y"], "k", lw=1)
            if ov["main_h"]:
                self.ax.plot(ov["main_h"]["x"], ov["main_h"]["y"], "k", lw=1)

        # Projection circle frame
        theta = np.linspace(0, 2 * np.pi, 200)
        self.ax.plot(np.cos(theta), np.sin(theta), "k", lw=2)
        # add clipping circle
        self.primitive = Circle(
            (0, 0),
            radius=1,
            edgecolor="black",
            fill=False,
            clip_box="None",
            label="_nolegend_",
        )
        self.ax.add_patch(self.primitive)

    def __plot_artists(self):
        for artist in self._artists:
            plot_method = getattr(self, artist["method"])
            args = tuple(self._data[obj_id] for obj_id in artist["args"])
            kwargs = artist["kwargs"]
            plot_method(*args, **kwargs)

    def __add_artist(self, method, args, kwargs):
        """Local data caching"""
        obj_ids = []
        for arg in args:
            obj_id = id(arg)
            if obj_id not in self._data:
                self._data[obj_id] = arg
            obj_ids.append(obj_id)
        self._artists.append(dict(method=method, args=obj_ids, kwargs=kwargs))

    def to_json(self):
        return dict(
            kwargs=self._kwargs,
            data={obj_id: obj.to_json() for obj_id, obj in self._data.items()},
            artists=self._artists,
        )

    @classmethod
    def from_json(cls, json_dict):
        def parse_json_data(obj_json):
            dtype_cls = getattr(sys.modules[__name__], obj_json["datatype"])
            args = []
            for arg in obj_json["args"]:
                if isinstance(arg, dict):
                    args.append([parse_json_data(jd) for jd in arg["collection"]])
                else:
                    args.append(arg)
            kwargs = obj_json.get("kwargs", {})
            return dtype_cls(*args, **kwargs)

        # parse
        s = cls(**json_dict["kwargs"])
        for obj_id, obj_json in json_dict["data"].items():
            s._data[obj_id] = parse_json_data(obj_json)
        s._artists = json_dict["artists"]
        return s

    def save(self, filename):
        with open(filename, "wb") as f:
            pickle.dump(self.to_json(), f, pickle.HIGHEST_PROTOCOL)

    @classmethod
    def load(cls, filename):
        with open(filename, "rb") as f:
            data = pickle.load(f)
        return cls.from_json(data)

    def show(self):
        self.__draw_net()
        self.__plot_artists()
        self.ax.set_xlim(-1.05, 1.05)
        self.ax.set_ylim(-1.05, 1.05)
        self.ax.legend(bbox_to_anchor=(1.05, 1.0), loc='upper left')
        h, labels = self.ax.get_legend_handles_labels()
        if h:
            lgd = self.ax.legend(
                h,
                labels,
                bbox_to_anchor=(1.05, 1),
                prop={"size": 11},
                loc=2,
                borderaxespad=0,
                scatterpoints=1,
                numpoints=1,
            )
        self.fig.tight_layout()
        # show
        plt.show()

    ########################################
    # PLOTTING METHODS                     #
    ########################################

    def __parse_default_linear_kwargs(self, kwargs):
        parsed = {}
        parsed["alpha"] = kwargs.get("alpha", None)
        if "color" in kwargs:
            parsed["mec"] = kwargs["color"]
            parsed["mfc"] = kwargs["color"]
        else:
            parsed["mec"] = kwargs.get("mec", None)
            parsed["mfc"] = kwargs.get("mfc", None)
        parsed["ls"] = kwargs.get("ls", "none")
        parsed["marker"] = kwargs.get("marker", "o")
        parsed["mew"] = kwargs.get("mew", 1)
        parsed["ms"] = kwargs.get("ms", 6)
        parsed["label"] = kwargs.get("label", None)
        return parsed

    def __parse_default_planar_kwargs(self, kwargs):
        parsed = {}
        parsed["alpha"] = kwargs.get("alpha", None)
        parsed["color"] = kwargs.get("color", None)
        parsed["ls"] = kwargs.get("ls", "-")
        parsed["lw"] = kwargs.get("lw", 1.5)
        parsed["marker"] = kwargs.get("marker", None)
        parsed["mec"] = kwargs.get("mec", None)
        parsed["mew"] = kwargs.get("mew", 1)
        parsed["mfc"] = kwargs.get("mfc", None)
        parsed["ms"] = kwargs.get("ms", 6)
        parsed["label"] = kwargs.get("label", None)
        return parsed

    # ----==== LINE ====---=

    def line(self, *args, **kwargs):
        """Plot linear feature(s) as point(s)"""
        if self.__validate_linear_args(args):
            kwargs = self.__parse_line_args(args, kwargs)
            self.__add_artist("_line", args, kwargs)

    def pole(self, *args, **kwargs):
        """Plot pole of planar feature(s) as point(s)"""
        if self.__validate_planar_args(args):
            kwargs = self.__parse_line_args(args, kwargs)
            self.__add_artist("_line", args, kwargs)

    def __validate_linear_args(self, args):
        if args:
            if all([issubclass(type(arg), (Vector3, Vector3Set)) for arg in args]):
                return True
            if self.show_warnings:
                print("Arguments must be Vector3 or Vector3Set like objects.")
        return False

    def __parse_line_args(self, args, kwargs):
        parsed = self.__parse_default_linear_kwargs(kwargs)
        if parsed["label"] is True:
            if len(args) == 1:
                parsed["label"] = args[0].label()
            else:
                parsed["label"] = f"Planar ({len(args)})"
        return parsed

    def _line(self, *args, **kwargs):
        x_lower, y_lower = self.proj.project_data(*np.vstack(args).T)
        x_upper, y_upper = self.proj.project_data(*(-np.vstack(args).T))
        handles = self.ax.plot(
            np.hstack((x_lower, x_upper)), np.hstack((y_lower, y_upper)), **kwargs
        )
        for h in handles:
            h.set_clip_path(self.primitive)

    # ----==== VECTOR ====---=

    def vector(self, *args, **kwargs):
        """Plot vector feature(s) as point(s), filled on lower and open on upper hemisphere."""
        if self.__validate_vector_args(args):
            kwargs = self.__parse_vector_args(args, kwargs)
            self.__add_artist("_vector", args, kwargs)

    def __validate_vector_args(self, args):
        if args:
            if all([issubclass(type(arg), (Vector3, Vector3Set)) for arg in args]):
                return True
            if self.show_warnings:
                print("Arguments must be Vector3 or Vector3Set like objects.")
        return False

    def __parse_vector_args(self, args, kwargs):
        parsed = self.__parse_default_linear_kwargs(kwargs)
        if parsed["label"] is True:
            if len(args) == 1:
                parsed["label"] = args[0].label()
            else:
                parsed["label"] = f"Vector ({len(args)})"
        return parsed

    def _vector(self, *args, **kwargs):
        x_lower, y_lower, x_upper, y_upper = self.proj.project_data_antipodal(
            *np.vstack(args).T
        )
        handles = self.ax.plot(x_lower, y_lower, **kwargs)
        for h in handles:
            h.set_clip_path(self.primitive)
        kwargs["label"] = None
        kwargs["color"] = h.get_color()
        kwargs["mfc"] = "none"
        handles = self.ax.plot(x_upper, y_upper, **kwargs)
        for h in handles:
            h.set_clip_path(self.primitive)

    # ----==== GREAT CIRCLE ====----

    def great_circle(self, *args, **kwargs):
        """Plot planar feature(s) as great circle(s)"""
        if self.__validate_great_circle_args(args):
            kwargs = self.__parse_great_circle_args(args, kwargs)
            self.__add_artist("_great_circle", args, kwargs)

    def __validate_great_circle_args(self, args):
        if args:
            if all([issubclass(type(arg), (Foliation, FoliationSet)) for arg in args]):
                return True
            if self.show_warnings:
                print("Arguments must be Foliation or FoliationSet like objects.")
        return False

    def __parse_great_circle_args(self, args, kwargs):
        parsed = self.__parse_default_planar_kwargs(kwargs)
        if parsed["label"] is True:
            if len(args) == 1:
                parsed["label"] = args[0].label()
            else:
                parsed["label"] = f"Planar ({len(args)})"
        return parsed

    def _great_circle(self, *args, **kwargs):
        X, Y = [], []
        for arg in args:
            if self.proj.rotate_data:
                fdv = arg.transform(self.proj.R).dipvec().transform(self.proj.Ri)
            else:
                fdv = arg.dipvec()
            # iterate
            for fol, dv in zip(np.atleast_2d(arg), np.atleast_2d(fdv)):
                # plot on lower
                x, y = self.proj.project_data(
                    *np.array(
                        [Vector3(dv).rotate(Vector3(fol), a) for a in self.angles_gc]
                    ).T
                )
                X.append(np.hstack((x, np.nan)))
                Y.append(np.hstack((y, np.nan)))
                # plot on upper
                x, y = self.proj.project_data(
                    *np.array(
                        [-Vector3(dv).rotate(Vector3(fol), a) for a in self.angles_gc]
                    ).T
                )
                X.append(np.hstack((x, np.nan)))
                Y.append(np.hstack((y, np.nan)))
        handles = self.ax.plot(np.hstack(X), np.hstack(Y), **kwargs)
        for h in handles:
            h.set_clip_path(self.primitive)

    # ----==== CONE ====---=

    def cone(self, *args, **kwargs):
        if self.__validate_cone_args(args):
            kwargs = self.__parse_cone_args(args, kwargs)
            self.__add_artist("_cone", args, kwargs)

    def __validate_cone_args(self, args):
        if len(args) == 2:
            if issubclass(type(args[0]), Vector3) and len(args) == 2:
                return True
            elif all(
                [issubclass(type(arg), (Vector3, Vector3Set)) for arg in args[0]]
            ) and len(args[0]) == len(args[1]):
                return True
            if self.show_warnings:
                print(
                    "First argument must be Vector3 or Vector3Set like objects and second scalar of same shape."
                )
        return False

    def __parse_cone_args(self, args, kwargs):
        parsed = self.__parse_default_planar_kwargs(kwargs)
        if parsed["label"] is True:
            if len(args[0]) == 1:
                parsed["label"] = f"Cone {str(args[0])} ({args[1]})"
            else:
                parsed["label"] = f"Cones ({len(args[0])})"
        return parsed

    def _cone(self, *args, **kwargs):
        X, Y = [], []
        for axis, angle in zip(np.atleast_2d(args[0]), np.atleast_1d(args[1])):
            if self.proj.rotate_data:
                lt = axis.transform(self.proj.R)
                azi, dip = Vector3(lt).geo
                cl_lower = Vector3(azi, dip + angle).transform(self.proj.Ri)
                cl_upper = -Vector3(azi, dip - angle).transform(self.proj.Ri)
            else:
                lt = axis
                azi, dip = Vector3(lt).geo
                cl_lower = Vector3(azi, dip + angle)
                cl_upper = -Vector3(azi, dip - angle)
            # plot on lower
            x, y = self.proj.project_data(
                *np.array([cl_lower.rotate(lt, a) for a in self.angles_sc]).T
            )
            X.append(np.hstack((x, np.nan)))
            Y.append(np.hstack((y, np.nan)))
            # plot on upper
            x, y = self.proj.project_data(
                *np.array([cl_upper.rotate(-lt, a) for a in self.angles_sc]).T
            )
            X.append(np.hstack((x, np.nan)))
            Y.append(np.hstack((y, np.nan)))
        handles = self.ax.plot(np.hstack(X), np.hstack(Y), **kwargs)
        for h in handles:
            h.set_clip_path(self.primitive)

    ########################################
    # CONTOURING                           #
    ########################################

    def __parse_default_contourf_kwargs(self, kwargs):
        parsed = {}
        parsed["alpha"] = kwargs.get("alpha", 1)
        parsed["antialiased"] = kwargs.get("antialiased", True)
        parsed["cmap"] = kwargs.get("cmap", "Greys")
        parsed["levels"] = kwargs.get("levels", 6)
        parsed["colorbar"] = kwargs.get("colorbar", False)
        parsed["label"] = kwargs.get("label", None)
        parsed["sigma"] = kwargs.get("sigma", None)
        parsed["trim"] = kwargs.get("trim", True)
        return parsed

    # ----==== CONTOURF ====---=

    def contourf(self, *args, **kwargs):
        if self.__validate_contourf_args(args):
            kwargs = self.__parse_contourf_args(args, kwargs)
            self.__add_artist("_contourf", args, kwargs)

    def __validate_contourf_args(self, args):
        if args:
            if all([issubclass(type(arg), Vector3Set) for arg in args]):
                return True
            if self.show_warnings:
                print("Argument must be Vector3Set like objects.")
        return False

    def __parse_contourf_args(self, args, kwargs):
        parsed = self.__parse_default_contourf_kwargs(kwargs)
        if parsed["label"] is True:
            if len(args) == 1:
                parsed["label"] = args[0].label()
            else:
                parsed["label"] = f"Planar ({len(args)})"
        return parsed

    def _contourf(self, *args, **kwargs):
        sigma = kwargs.pop("sigma")
        trim = kwargs.pop("trim")
        self.stereogrid.calculate_density(args[0], sigma=sigma, trim=trim)
        dcgrid = np.asarray(self.stereogrid.grid).T
        X, Y = self.proj.project_data(*dcgrid, clip_inside=False)
        colorbar = kwargs.pop("colorbar")
        label = kwargs.pop("label")
        cf = self.ax.tricontourf(X, Y, self.stereogrid.values, **kwargs)
        for collection in cf.collections:
            collection.set_clip_path(self.primitive)
        if colorbar:
            self.fig.colorbar(cf, ax=self.ax, label=label, shrink=0.6)
        # plt.colorbar(cf, format="%3.2f", spacing="proportional")


class RosePlot(object):

    """
    ``RosePlot`` class for rose histogram plotting.

    Args:
        any plottable APSG class (most of data classes and tensors)

    Keyword Args:
        title: figure title. Default ''
        figsize: Figure size. Default from settings ()
        axial: Directional data are axial. Defaut True
        density: Use density instead of counts. Default False
        pdf: Plot Von Mises density function instead histogram. Default False
        kappa; Shape parameter of Von Mises pdf. Default 250
        scaled: Bins scaled by area instead value. Default False
        arrow: Bar arrowness. (0-1) Default 0.95
        rwidth: Bar width (0-1). Default 1
        ticks: show ticks. Default True
        grid: show grid lines. Default False
        grid_kw: Dict passed to Axes.grid. Default {}

        Other keyword arguments are passed to matplotlib plot.

    Examples:
        >>> g = Group.randn_fol(mean=fol(120, 0))
        >>> direction, dip  = g.rhr
        >>> RosePlot(direction)
        >>> RosePlot(direction, density=True)
        >>> RosePlot(direction, pdf=True)
        >>> s = RosePlot()
        >>> s.plot(direction, color='r')
        >>> s.show()
    """

    def __init__(self, *args, **kwargs):
        self.fig = plt.figure(figsize=kwargs.pop("figsize", settings["figsize"]))
        self.fig.canvas.set_window_title("Rose plot")
        self.bins = kwargs.get("bins", 36)
        self.axial = kwargs.get("axial", True)
        self.pdf = kwargs.get("pdf", False)
        self.kappa = kwargs.get("kappa", 250)
        self.density = kwargs.get("density", False)
        self.arrow = kwargs.get("arrow", 0.95)
        self.rwidth = kwargs.get("rwidth", 1)
        self.scaled = kwargs.get("scaled", False)
        self.title_text = kwargs.get("title", "")
        self.grid = kwargs.get("grid", True)
        self.grid_kw = kwargs.get("grid_kw", {})
        self.fill_kw = kwargs.get("fill_kw", {})
        self.cla()
        # optionally immidiately plot passed objects
        if args:
            for arg in args:
                self.plot(arg)
            self.show()

    def cla(self):
        """Clear projection."""

        self.fig.clear()
        self.ax = self.fig.add_subplot(111, polar=True)
        # self.ax.format_coord = self.format_coord
        self.ax.set_theta_direction(-1)
        self.ax.set_theta_zero_location("N")
        self.ax.grid(self.grid, **self.grid_kw)
        self.fig.suptitle(self.title_text)

    def plot(self, obj, *args, **kwargs):
        if type(obj) is FeatureSet:
            ang, _ = obj.dd
            weights = abs(obj)
            self.title_text = obj.name
        else:
            ang = np.array(obj)
            weights = None
        if "weights" in kwargs:
            weights = kwargs.pop("weights")

        if self.axial:
            ang = np.concatenate((ang % 360, (ang + 180) % 360))
            if weights is not None:
                weights = np.concatenate((weights, weights))

        if self.pdf:
            theta = np.linspace(-np.pi, np.pi, 1801)
            radii = np.zeros_like(theta)
            for a in ang:
                radii += vonmises.pdf(theta, self.kappa, loc=np.radians(a % 360))
            radii /= len(ang)
        else:
            width = 360 / self.bins
            if weights is not None:
                num, bin_edges = np.histogram(
                    ang,
                    bins=self.bins + 1,
                    range=(-width / 2, 360 + width / 2),
                    weights=weights,
                    density=self.density,
                )
            else:
                num, bin_edges = np.histogram(
                    ang,
                    bins=self.bins + 1,
                    range=(-width / 2, 360 + width / 2),
                    density=self.density,
                )
            num[0] += num[-1]
            num = num[:-1]
            theta, radii = [], []
            for cc, val in zip(np.arange(0, 360, width), num):
                theta.extend(
                    [
                        cc - width / 2,
                        cc - self.rwidth * width / 2,
                        cc,
                        cc + self.rwidth * width / 2,
                        cc + width / 2,
                    ]
                )
                radii.extend([0, val * self.arrow, val, val * self.arrow, 0])
            theta = np.deg2rad(theta)
        if self.scaled:
            radii = np.sqrt(radii)
        fill_kw = self.fill_kw.copy()
        fill_kw.update(kwargs)
        self.ax.fill(theta, radii, **fill_kw)

    def close(self):
        plt.close(self.fig)

    def show(self):
        plt.show()

    def savefig(self, filename="apsg_roseplot.pdf", **kwargs):
        self.ax.figure.savefig(filename, **kwargs)


class _FabricPlot(object):

    """
    Metaclas for Fabric plots
    """

    def close(self):
        plt.close(self.fig)

    @property
    def closed(self):
        return not plt.fignum_exists(self.fig.number)

    def draw(self):
        if self.closed:
            print(
                "The DeformationPlot figure have been closed. "
                "Use new() method or create new one."
            )
        else:
            h, lbls = self.ax.get_legend_handles_labels()
            if h:
                self._lgd = self.ax.legend(
                    h,
                    lbls,
                    prop={"size": 11},
                    borderaxespad=0,
                    loc="center left",
                    bbox_to_anchor=(1.1, 0.5),
                    scatterpoints=1,
                    numpoints=1,
                )
            plt.draw()

    def new(self):
        """
        Re-initialize figure.
        """

        if self.closed:
            self.__init__()

    def show(self):
        plt.show()

    def savefig(self, filename="apsg_fabricplot.pdf", **kwargs):
        if self._lgd is None:
            self.ax.figure.savefig(filename, **kwargs)
        else:
            self.ax.figure.savefig(
                filename, bbox_extra_artists=(self._lgd,), bbox_inches="tight", **kwargs
            )


class VollmerPlot(_FabricPlot):

    """
    Represents the triangular fabric plot (Vollmer, 1989).
    """

    def __init__(self, *args, **kwargs):
        self.fig = plt.figure(figsize=kwargs.pop("figsize", settings["figsize"]))
        self.fig.canvas.set_window_title("Vollmer fabric plot")
        self.ticks = kwargs.get("ticks", True)
        self.grid = kwargs.get("grid", True)
        self.grid_style = kwargs.get("grid_style", "k:")
        self._lgd = None
        self.A = np.asarray(kwargs.get("A", [0, 3 ** 0.5 / 2]))
        self.B = np.asarray(kwargs.get("B", [1, 3 ** 0.5 / 2]))
        self.C = np.asarray(kwargs.get("C", [0.5, 0]))
        self.Ti = np.linalg.inv(np.array([self.A - self.C, self.B - self.C]).T)
        self.cla()
        # optionally immidiately plot passed objects
        if args:
            for arg in args:
                self.plot(arg)
            self.show()

    def cla(self):
        """Clear projection."""

        self.fig.clear()
        self.ax = self.fig.add_subplot(111)
        self.ax.format_coord = self.format_coord
        self.ax.set_aspect("equal")
        self.ax.set_autoscale_on(False)

        triangle = np.c_[self.A, self.B, self.C, self.A]
        n = 10
        tick_size = 0.2
        margin = 0.05

        self.ax.set_axis_off()

        plt.axis(
            [
                self.A[0] - margin,
                self.B[0] + margin,
                self.C[1] - margin,
                self.A[1] + margin,
            ]
        )

        # projection triangle
        bg = plt.Polygon([self.A, self.B, self.C], color="w", edgecolor=None)

        self.ax.add_patch(bg)
        self.ax.plot(triangle[0], triangle[1], "k", lw=2)
        self.ax.text(
            self.A[0] - 0.02, self.A[1], "P", ha="right", va="bottom", fontsize=14
        )
        self.ax.text(
            self.B[0] + 0.02, self.B[1], "G", ha="left", va="bottom", fontsize=14
        )
        self.ax.text(
            self.C[0], self.C[1] - 0.02, "R", ha="center", va="top", fontsize=14
        )

        if self.grid:
            for l in np.arange(0.1, 1, 0.1):
                self.triplot([l, l], [0, 1 - l], [1 - l, 0], "k:")
                self.triplot([0, 1 - l], [l, l], [1 - l, 0], "k:")
                self.triplot([0, 1 - l], [1 - l, 0], [l, l], "k:")

        # ticks
        if self.ticks:
            r = np.linspace(0, 1, n + 1)
            tick = tick_size * (self.B - self.C) / n
            x = self.A[0] * (1 - r) + self.B[0] * r
            x = np.vstack((x, x + tick[0]))
            y = self.A[1] * (1 - r) + self.B[1] * r
            y = np.vstack((y, y + tick[1]))
            self.ax.plot(x, y, "k", lw=1)
            tick = tick_size * (self.C - self.A) / n
            x = self.B[0] * (1 - r) + self.C[0] * r
            x = np.vstack((x, x + tick[0]))
            y = self.B[1] * (1 - r) + self.C[1] * r
            y = np.vstack((y, y + tick[1]))
            self.ax.plot(x, y, "k", lw=1)
            tick = tick_size * (self.A - self.B) / n
            x = self.A[0] * (1 - r) + self.C[0] * r
            x = np.vstack((x, x + tick[0]))
            y = self.A[1] * (1 - r) + self.C[1] * r
            y = np.vstack((y, y + tick[1]))
            self.ax.plot(x, y, "k", lw=1)

        self.ax.set_title("Fabric plot")

        self.draw()

    def triplot(self, a, b, c, *args, **kwargs):

        a = np.asarray(a)
        b = np.asarray(b)
        c = np.asarray(c)
        x = (a * self.A[0] + b * self.B[0] + c * self.C[0]) / (a + b + c)
        y = (a * self.A[1] + b * self.B[1] + c * self.C[1]) / (a + b + c)

        self.ax.plot(x, y, *args, **kwargs)

        self.draw()

    def plot(self, obj, *args, **kwargs):
        if type(obj) is FeatureSet:
            obj = obj.ortensor

        if not isinstance(obj, Tensor):
            raise TypeError("%s argument is not supported!" % type(obj))

        # ensure point plot
        if "ls" not in kwargs and "linestyle" not in kwargs:
            kwargs["linestyle"] = "none"

        if not args:
            if "marker" not in kwargs:
                kwargs["marker"] = "o"
        if "label" not in kwargs:
            kwargs["label"] = obj.name

        self.triplot(obj.P, obj.G, obj.R, *args, **kwargs)

        self.draw()

    def path(self, objs, *args, **kwargs):
        # ensure point plot
        if "ls" not in kwargs and "linestyle" not in kwargs:
            kwargs["linestyle"] = "-"

        if not args:
            if "marker" not in kwargs:
                kwargs["marker"] = "."

        P = [obj.P for obj in objs]
        G = [obj.G for obj in objs]
        R = [obj.R for obj in objs]

        self.triplot(P, G, R, *args, **kwargs)

        self.draw()

    def format_coord(self, x, y):
        a, b = self.Ti.dot(np.r_[x, y] - self.C)
        c = 1 - a - b
        if a < 0 or b < 0 or c < 0:
            return ""
        else:
            return "P:{:0.2f} G:{:0.2f} R:{:0.2f}".format(a, b, c)


class RamsayPlot(_FabricPlot):

    """
    Represents the Ramsay deformation plot.
    """

    def __init__(self, *args, **kwargs):
        self.fig = plt.figure(figsize=kwargs.pop("figsize", settings["figsize"]))
        self.fig.canvas.set_window_title("Ramsay deformation plot")
        self.ticks = kwargs.get("ticks", True)
        self.grid = kwargs.get("grid", False)
        self.grid_style = kwargs.get("grid_style", "k:")
        self._lgd = None
        self.cla()
        # optionally immidiately plot passed objects
        if args:
            for arg in args:
                self.plot(arg)
            self.show()

    def cla(self):
        """Clear projection."""

        self.fig.clear()
        self.ax = self.fig.add_subplot(111)
        self.ax.format_coord = self.format_coord
        self.ax.set_aspect("equal")
        self.ax.set_autoscale_on(True)
        self.ax.spines["top"].set_color("none")
        self.ax.spines["right"].set_color("none")
        self.ax.set_xlabel(r"$\varepsilon_2-\varepsilon_3$")
        self.ax.set_ylabel(r"$\varepsilon_1-\varepsilon_2$")
        self.ax.grid(self.grid)

        self.ax.set_title("Ramsay plot")

        self.draw()

    def plot(self, obj, *args, **kwargs):
        if type(obj) is FeatureSet:
            obj = obj.ortensor

        if not isinstance(obj, Tensor):
            raise TypeError("%s argument is not supported!" % type(obj))

        # ensure point plot
        if "ls" not in kwargs and "linestyle" not in kwargs:
            kwargs["linestyle"] = "none"

        if not args:
            if "marker" not in kwargs:
                kwargs["marker"] = "o"
        if "label" not in kwargs:
            kwargs["label"] = obj.name

        self.ax.plot(obj.e23, obj.e12, *args, **kwargs)

        self.draw()

    def path(self, objs, *args, **kwargs):
        # ensure point plot
        if "ls" not in kwargs and "linestyle" not in kwargs:
            kwargs["linestyle"] = "-"

        if not args:
            if "marker" not in kwargs:
                kwargs["marker"] = "."
        # if "label" not in kwargs:
        #    kwargs["label"] = obj.name

        e23 = [obj.e23 for obj in objs]
        e12 = [obj.e12 for obj in objs]

        self.ax.plot(e23, e12, *args, **kwargs)

        self.draw()

    def show(self):
        mx = max(self.ax.get_xlim()[1], self.ax.get_ylim()[1])
        self.ax.set_xlim(0, mx)
        self.ax.set_ylim(0, mx)
        self.ax.plot([0, mx], [0, mx], "k", lw=0.5)
        box = self.ax.get_position()
        self.ax.set_position([box.x0, box.y0, box.width * 0.8, box.height])
        plt.show()

    def format_coord(self, x, y):
        k = y / x if x > 0 else 0
        d = x ** 2 + y ** 2
        return "k:{:0.2f} d:{:0.2f}".format(k, d)


class FlinnPlot(_FabricPlot):

    """
    Represents the Ramsay deformation plot.
    """

    def __init__(self, *args, **kwargs):
        self.fig = plt.figure(figsize=kwargs.pop("figsize", settings["figsize"]))
        self.fig.canvas.set_window_title("Flinn's deformation plot")
        self.ticks = kwargs.get("ticks", True)
        self.grid = kwargs.get("grid", False)
        self.grid_style = kwargs.get("grid_style", "k:")
        self._lgd = None
        self.cla()
        # optionally immidiately plot passed objects
        if args:
            for arg in args:
                self.plot(arg)
            self.show()

    def cla(self):
        """Clear projection."""

        self.fig.clear()
        self.ax = self.fig.add_subplot(111)
        self.ax.format_coord = self.format_coord
        self.ax.set_aspect("equal")
        self.ax.set_autoscale_on(True)
        self.ax.spines["top"].set_color("none")
        self.ax.spines["right"].set_color("none")
        self.ax.set_xlabel(r"$R_{YZ}$")
        self.ax.set_ylabel(r"$R_{XY}$")
        self.ax.grid(self.grid)

        self.ax.set_title("Flinn's plot")

        self.draw()

    def plot(self, obj, *args, **kwargs):
        if type(obj) is FeatureSet:
            obj = obj.ortensor

        if not isinstance(obj, Tensor):
            raise TypeError("%s argument is not supported!" % type(obj))

        # ensure point plot
        if "ls" not in kwargs and "linestyle" not in kwargs:
            kwargs["linestyle"] = "none"

        if not args:
            if "marker" not in kwargs:
                kwargs["marker"] = "o"
        if "label" not in kwargs:
            kwargs["label"] = obj.name

        self.ax.plot(obj.Ryz, obj.Rxy, *args, **kwargs)

        self.draw()

    def path(self, objs, *args, **kwargs):
        # ensure point plot
        if "ls" not in kwargs and "linestyle" not in kwargs:
            kwargs["linestyle"] = "-"

        if not args:
            if "marker" not in kwargs:
                kwargs["marker"] = "."
        # if "label" not in kwargs:
        #    kwargs["label"] = obj.name

        Ryz = [obj.Ryz for obj in objs]
        Rxy = [obj.Rxy for obj in objs]

        self.ax.plot(Ryz, Rxy, *args, **kwargs)

        self.draw()

    def show(self):
        mx = max(self.ax.get_xlim()[1], self.ax.get_ylim()[1])
        self.ax.set_xlim(1, mx)
        self.ax.set_ylim(1, mx)
        self.ax.plot([1, mx], [1, mx], "k", lw=0.5)
        box = self.ax.get_position()
        self.ax.set_position([box.x0, box.y0, box.width * 0.8, box.height])
        plt.show()

    def format_coord(self, x, y):
        K = (y - 1) / (x - 1) if x > 1 else 0
        D = np.sqrt((x - 1) ** 2 + (y - 1) ** 2)
        return "K:{:0.2f} D:{:0.2f}".format(K, D)


class HsuPlot(_FabricPlot):

    """
    Represents the Hsu fabric plot.
    """

    def __init__(self, *args, **kwargs):
        self.fig = plt.figure(figsize=kwargs.pop("figsize", settings["figsize"]))
        self.fig.canvas.set_window_title("Hsu fabric plot")
        self.ticks = kwargs.get("ticks", True)
        self.grid = kwargs.get("grid", True)
        self.grid_style = kwargs.get("grid_style", "k:")
        self._lgd = None
        self.cla()
        # optionally immidiately plot passed objects
        if args:
            for arg in args:
                self.plot(arg)
            self.show()

    def cla(self):
        """Clear projection."""

        self.fig.clear()
        self.ax = self.fig.add_subplot(111, polar=True)
        # self.ax.format_coord = self.format_coord
        self.ax.set_theta_zero_location("N")
        self.ax.set_theta_direction(-1)
        self.ax.set_thetamin(-30)
        self.ax.set_thetamax(30)
        self.ax.set_xticks([-np.pi / 6, -np.pi / 12, 0, np.pi / 12, np.pi / 6])
        self.ax.set_xticklabels([-1, -0.5, 0, 0.5, 1])
        self.ax.set_title(r"$\nu$")
        self.ax.set_ylabel(r"$\bar{\varepsilon}_s$")
        self.ax.grid(self.grid)

        self.draw()

    def plot(self, obj, *args, **kwargs):
        if type(obj) is FeatureSet:
            obj = obj.ortensor

        if not isinstance(obj, Tensor):
            raise TypeError("%s argument is not supported!" % type(obj))

        # ensure point plot
        if "ls" not in kwargs and "linestyle" not in kwargs:
            kwargs["linestyle"] = "none"

        if not args:
            if "marker" not in kwargs:
                kwargs["marker"] = "o"
        if "label" not in kwargs:
            kwargs["label"] = obj.name

        self.ax.plot(obj.lode * np.pi / 6, obj.eoct, *args, **kwargs)

        self.draw()

    def path(self, objs, *args, **kwargs):
        # ensure point plot
        if "ls" not in kwargs and "linestyle" not in kwargs:
            kwargs["linestyle"] = "-"

        if not args:
            if "marker" not in kwargs:
                kwargs["marker"] = "."
        # if "label" not in kwargs:
        #    kwargs["label"] = obj.name

        lode = [obj.lode * np.pi / 6 for obj in objs]
        eoct = [obj.eoct for obj in objs]

        self.ax.plot(lode, eoct, *args, **kwargs)

        self.draw()

    def format_coord(self, x, y):
        K = (y - 1) / (x - 1) if x > 1 else 0
        D = np.sqrt((x - 1) ** 2 + (y - 1) ** 2)
        return "K:{:0.2f} D:{:0.2f}".format(K, D)


##############################################
#   THIS IS DEPRECATED AND WILL BE REMOVED   #
##############################################


class StereoNetOld(object):

    """
    ``StereoNet`` class for Schmidt net plotting.

    A stereonet is a lower hemisphere Schmidt net on to which a variety
    of geological data can be plotted.

    If args are provided plot is immediately shown. If no args are provided,
    following methods and properties could be used for additional operations.

    Args:
        any plottable APSG class (most of data classes and tensors)

    Keyword Args:
        fol_plot: default method for ``Fol`` instances. ['plane' or 'pole']
                  Default 'plane'
        title: figure title. Default ''
        figsize: Figure size. Default from settings ()
        ncols: number of subplot columns. Default 1
        ticks: show ticks. Default True
        grid: show grid lines. Default False
        gridlw: grid lines width. Default 1
        grid_style: grid lines style. Default 'k:'
        cbpad: colorbar padding. Default 0.1

        Other keyword arguments are passed to matplotlib plot.

    Example:
        >>> s = StereoNet()
        >>> g = Group.randn_lin(mean=lin(40, 20))
        >>> s.contourf(g, 8, legend=True, sigma=2)
        >>> s.line(g, 'g.', label='My data')
        >>> s.show()
    """

    def __init__(self, *args, **kwargs):
        self.ticks = kwargs.pop("ticks", True)
        self.grid = kwargs.pop("grid", False)
        self.gridlw = kwargs.pop("gridlw", 1)
        self.ncols = kwargs.pop("ncols", 1)
        self.cbpad = kwargs.pop("cbpad", 0.1)
        self.grid_style = kwargs.pop("grid_style", "k:")
        self.fol_plot = kwargs.pop("fol_plot", "plane")
        figsize = kwargs.pop("figsize", settings["figsize"])
        self._title_text = kwargs.pop("title", "")
        self._lgd = None
        self.active = 0
        self.artists = []
        self.fig, self.ax = plt.subplots(ncols=self.ncols, figsize=figsize)
        self.fig.canvas.set_window_title("StereoNet - Schmidt projection")
        # self.fig.set_size_inches(8 * self.ncols, 6)
        self._axtitle = self.ncols * [None]
        self.artist_collection = []
        self.artist_labels = []
        self.cid = None
        self.cla()
        # optionally immidiately plot passed objects
        if args:
            for arg in args:
                kwargs["label"] = repr(arg)
                if type(arg) in [Group, PairSet, FaultSet]:
                    typ = arg.type
                else:
                    typ = type(arg)
                if typ is Lin:
                    self.line(arg, **kwargs)
                elif typ is Fol:
                    getattr(self, self.fol_plot)(arg, **kwargs)
                elif typ is Vector3:
                    self.vector(arg.aslin, **kwargs)
                elif typ is Pair:
                    self.pair(arg, **kwargs)
                elif typ is Fault:
                    self.fault(arg, **kwargs)
                elif typ is StereoGrid:
                    kwargs.pop("label", None)
                    kwargs.pop("legend", None)
                    self.contourf(arg, legend=True, **kwargs)
                elif typ in [Ortensor, Ellipsoid, DefGrad, Stress]:
                    kwargs.pop("label", None)
                    self.tensor(arg, **kwargs)
                else:
                    raise TypeError("%s argument is not supported!" % typ)
            self.show()

    def close(self):
        plt.close(self.fig)

    @property
    def closed(self):
        return not plt.fignum_exists(self.fig.number)

    def draw(self):
        if self.closed:
            print(
                "The StereoNet figure have been closed. "
                "Use new() method or create new one."
            )
        else:
            for ax in self.fig.axes:
                h, lbls = ax.get_legend_handles_labels()
                if h:
                    self._lgd = ax.legend(
                        h,
                        lbls,
                        bbox_to_anchor=(1.12, 1),
                        prop={"size": 11},
                        loc=2,
                        borderaxespad=0,
                        scatterpoints=1,
                        numpoints=1,
                    )
                    plt.subplots_adjust(right=0.75)
                else:
                    plt.subplots_adjust(right=0.9)
            plt.draw()
            # plt.pause(0.001)

    def new(self):
        """Re-initialize existing StereoNet."""
        if self.closed:
            self.__init__()

    def cla(self):
        """Clear axes and draw empty projection."""

        def lat(a, phi):
            return self._cone(l2v(a, 0), l2v(a, phi), limit=89.9999, res=91)

        def lon(a, theta):
            return self._cone(p2v(a, theta), l2v(a, theta), limit=80, res=91)

        # recreate default Axes
        self.fig.clear()
        self.ax = self.fig.subplots(ncols=self.ncols)
        self.annot = []
        for ax in self.fig.axes:
            ax.cla()
            ax.format_coord = self.format_coord
            ax.set_aspect("equal")
            ax.set_autoscale_on(False)
            ax.axis([-1.05, 1.05, -1.05, 1.05])
            ax.set_axis_off()

            # Projection circle
            ax.text(0, 1.02, "N", ha="center", va="baseline", fontsize=16)
            ax.add_artist(plt.Circle((0, 0), 1, color="w", zorder=0))
            ax.add_artist(plt.Circle((0, 0), 1, color="None", ec="k", zorder=3))

            if self.grid:
                # Main cross
                ax.plot(
                    [-1, 1, np.nan, 0, 0],
                    [0, 0, np.nan, -1, 1],
                    self.grid_style,
                    zorder=3,
                    lw=self.gridlw,
                )
                # Latitudes
                lat_n = np.array([lat(0, phi) for phi in range(10, 90, 10)])
                ax.plot(
                    lat_n[:, 0, :].T,
                    lat_n[:, 1, :].T,
                    self.grid_style,
                    zorder=3,
                    lw=self.gridlw,
                )
                lat_s = np.array([lat(180, phi) for phi in range(10, 90, 10)])
                ax.plot(
                    lat_s[:, 0, :].T,
                    lat_s[:, 1, :].T,
                    self.grid_style,
                    zorder=3,
                    lw=self.gridlw,
                )
                # Longitudes
                le = np.array([lon(90, theta) for theta in range(10, 90, 10)])
                ax.plot(
                    le[:, 0, :].T,
                    le[:, 1, :].T,
                    self.grid_style,
                    zorder=3,
                    lw=self.gridlw,
                )
                lw = np.array([lon(270, theta) for theta in range(10, 90, 10)])
                ax.plot(
                    lw[:, 0, :].T,
                    lw[:, 1, :].T,
                    self.grid_style,
                    zorder=3,
                    lw=self.gridlw,
                )

            # ticks
            if self.ticks:
                a = np.arange(0, 360, 30)
                tt = np.array([0.98, 1])
                x = np.outer(tt, sind(a))
                y = np.outer(tt, cosd(a))
                ax.plot(x, y, "k", zorder=4)
            # Middle cross
            ax.plot(
                [-0.02, 0.02, np.nan, 0, 0], [0, 0, np.nan, -0.02, 0.02], "k", zorder=4
            )
            annot = ax.annotate(
                "",
                xy=(0, 0),
                xytext=(20, 20),
                textcoords="offset points",
                arrowprops=dict(arrowstyle="->"),
                zorder=10,
                bbox=dict(boxstyle="round", fc="w"),
            )
            annot.set_visible(False)
            self.annot.append(annot)
        self._title = self.fig.suptitle(self._title_text)
        self.draw()

    def getlin(self):
        """Get Lin instance by mouse click."""
        x, y = plt.ginput(1)[0]
        return Lin(*getldd(x, y))

    def getfol(self):
        """Get Fol instance by mouse click."""
        x, y = plt.ginput(1)[0]
        return Fol(*getfdd(x, y))

    def getlins(self):
        """Get Group of Lin by mouse clicks."""
        pts = plt.ginput(0, mouse_add=1, mouse_pop=2, mouse_stop=3)
        return Group([Lin(*getldd(x, y)) for x, y in pts])

    def getfols(self):
        """Get Group of Fol by mouse clicks."""
        pts = plt.ginput(0, mouse_add=1, mouse_pop=2, mouse_stop=3)
        return Group([Fol(*getfdd(x, y)) for x, y in pts])

    def _cone(self, axis, vector, limit=180, res=361, split=False):
        a = np.linspace(-limit, limit, res)
        x, y = l2xy(*v2l(rodrigues(axis, vector, a)))
        if split:
            dist = np.hypot(np.diff(x), np.diff(y))
            ix = np.nonzero(dist > 1)[0]
            x = np.insert(x, ix + 1, np.nan)
            y = np.insert(y, ix + 1, np.nan)
        return x, y

    def _arrow(self, pos_lin, dir_lin=None, sense=1):
        x, y = l2xy(*pos_lin.dd)
        if dir_lin is None:
            dx, dy = -x, -y
        else:
            ax, ay = l2xy(*dir_lin.dd)
            dx, dy = -ax, -ay
        mag = np.hypot(dx, dy)
        u, v = sense * dx / mag, sense * dy / mag
        return x, y, u, v

    def arrow(self, pos_lin, dir_lin=None, sense=1, **kwargs):
        """Draw arrow at given position in given direction."""
        animate = kwargs.pop("animate", False)
        x, y, u, v = self._arrow(pos_lin, dir_lin, sense=sense)
        a = self.fig.axes[self.active].quiver(
            x, y, u, v, width=2, headwidth=5, zorder=6, pivot="mid", units="dots"
        )
        p = self.fig.axes[self.active].scatter(x, y, color="k", s=5, zorder=6)
        if animate:
            self.artists.append(tuple(a + p))
        self.draw()

    def arc(self, l1, l2, *args, **kwargs):
        """Draw great circle segment between two points."""
        assert issubclass(type(l1), Vector3) and issubclass(
            type(l2), Vector3
        ), "Arguments must be subclass of Vector3"
        animate = kwargs.pop("animate", False)
        angstep = kwargs.pop("angstep", 1)
        ax, phi = l1.H(l2).axisangle
        steps = abs(int(phi / angstep))
        angles = np.linspace(0, phi, steps)
        rv = [l1.rotate(ax, angle) for angle in angles]
        lh = [vv.flip if vv.upper else vv for vv in rv]  # what about Vector3?
        x, y = l2xy(*np.array([v.dd for v in lh]).T)
        h = self.fig.axes[self.active].plot(x, y, *args, **kwargs)
        if animate:
            self.artists.append(tuple(h))
        self.draw()

    def polygon(self, *args, **kwargs):
        """Draw filled polygon defined by series of points or planes."""
        assert len(args) > 2, "More than 2 arguments needed"
        animate = kwargs.pop("animate", False)
        angstep = kwargs.pop("angstep", 1)
        coords = []
        g = Group(list(args))
        assert issubclass(
            g.type, Vector3
        ), "Only Vector3-like instances could be plotted as polygon."
        if g.type is Fol:
            g = Group([f1 ** f2 for f1, f2 in zip(g, g[1:] + g[:1])])
        for l1, l2 in zip(g, g[1:] + g[:1]):
            ax, phi = l1.H(l2).axisangle
            steps = abs(int(phi / angstep))
            angles = np.linspace(0, phi, steps)
            rv = [l1.rotate(ax, angle) for angle in angles]
            lh = [vv.flip if vv.upper else vv for vv in rv]  # what about Vector3?
            coords.extend(np.transpose(l2xy(*np.array([v.dd for v in lh]).T)))
        bg = plt.Polygon(coords, **kwargs)
        h = self.ax.add_patch(bg)
        if animate:
            self.artists.append(tuple(h))
        self.draw()

    def plane(self, obj, *args, **kwargs):
        """Draw Fol as great circle."""
        assert obj.type is Fol, "Only Fol type instance could be plotted as plane."
        if "zorder" not in kwargs:
            kwargs["zorder"] = 5
        animate = kwargs.pop("animate", False)
        if isinstance(obj, Group):
            x = []
            y = []
            for azi, inc in obj.dd.T:
                xx, yy = self._cone(
                    p2v(azi, inc),
                    l2v(azi, inc),
                    limit=89.9999,
                    res=int(cosd(inc) * 179 + 2),
                )
                x = np.hstack((x, xx, np.nan))
                y = np.hstack((y, yy, np.nan))
            x = x[:-1]
            y = y[:-1]
        else:
            azi, inc = obj.dd
            x, y = self._cone(
                p2v(azi, inc),
                l2v(azi, inc),
                limit=89.9999,
                res=int(cosd(inc) * 179 + 2),
            )
        h = self.fig.axes[self.active].plot(x, y, *args, **kwargs)
        if animate:
            self.artists.append(tuple(h))
        self.draw()

    def line(self, obj, *args, **kwargs):
        """Draw Lin as point."""
        assert obj.type is Lin, "Only Lin type instance could be plotted as line."
        if "zorder" not in kwargs:
            kwargs["zorder"] = 5
        animate = kwargs.pop("animate", False)
        # ensure point plot
        if "ls" not in kwargs and "linestyle" not in kwargs:
            kwargs["linestyle"] = "none"
        if not args:
            if "marker" not in kwargs:
                kwargs["marker"] = "o"
        x, y = l2xy(*obj.dd)
        h = self.fig.axes[self.active].plot(x, y, *args, **kwargs)
        if animate:
            self.artists.append(tuple(h))
        self.draw()

    def scatter(self, obj, *args, **kwargs):
        """Draw Lin as point with varying marker size and/or color."""
        assert obj.type in [
            Lin,
            Fol,
            Vector3,
        ], "Only Vector3, Lin or Fol type instance could be plotted with scatter."
        if "zorder" not in kwargs:
            kwargs["zorder"] = 5
        if "legend" in kwargs:
            legend = kwargs.pop("legend")
        else:
            legend = False
        animate = kwargs.pop("animate", False)
        labels = kwargs.pop("labels", False)
        if not args:
            if "marker" not in kwargs:
                kwargs["marker"] = "o"
        x, y = l2xy(*obj.aslin.dd)
        h = self.fig.axes[self.active].scatter(x, y, *args, **kwargs)
        if labels:
            assert len(h.get_offsets()) == len(
                labels
            ), "Number of labels is not the same as the number of data."
            self.artist_collection.append(h)
            self.artist_labels.append(labels)
            if self.cid is None:
                self.cid = self.fig.canvas.mpl_connect(
                    "motion_notify_event", self.hover
                )
        if legend:
            self.fig.colorbar(h)
        if animate:
            self.artists.append(tuple(h))
        self.draw()

    def vector(self, obj, *args, **kwargs):
        """ This mimics plotting on lower and upper hemisphere using
        full and hollow symbols."""
        assert issubclass(
            obj.type, Vector3
        ), "Only Vector3-like instance could be plotted as line."
        if "zorder" not in kwargs:
            kwargs["zorder"] = 5
        animate = kwargs.pop("animate", False)
        # ensure point plot
        if "ls" not in kwargs and "linestyle" not in kwargs:
            kwargs["linestyle"] = "none"
        if not args:
            if "marker" not in kwargs:
                kwargs["marker"] = "o"
        if isinstance(obj, Group):
            uh = obj.upper
            if np.any(~uh):
                x, y = l2xy(*obj[~uh].dd)
                h1 = self.fig.axes[self.active].plot(x, y, *args, **kwargs)
                kwargs.pop("label", None)
                cc = h1[0].get_color()
            else:
                cc = None
            if np.any(uh):
                kwargs["fillstyle"] = "none"
                x, y = l2xy(*obj[uh].flip.dd)
                h2 = self.fig.axes[self.active].plot(x, y, *args, **kwargs)
                if cc is not None:
                    h2[0].set_color(cc)
            if animate:
                self.artists.append(tuple(h1 + h2))
        else:
            if obj.upper:
                kwargs["fillstyle"] = "none"
                x, y = l2xy(*obj.flip.dd)
                h = self.fig.axes[self.active].plot(x, y, *args, **kwargs)
            else:
                x, y = l2xy(*obj.dd)
                h = self.fig.axes[self.active].plot(x, y, *args, **kwargs)
            if animate:
                self.artists.append(tuple(h))
        self.draw()

    def pole(self, obj, *args, **kwargs):
        """Draw Fol as pole."""
        assert obj.type is Fol, "Only Fol type instance could be plotted as poles."
        if "zorder" not in kwargs:
            kwargs["zorder"] = 5
        animate = kwargs.pop("animate", False)
        # ensure point plot
        if "ls" not in kwargs and "linestyle" not in kwargs:
            kwargs["linestyle"] = "none"
        if not args:
            if "marker" not in kwargs:
                kwargs["marker"] = "s"
        x, y = l2xy(*obj.aslin.dd)
        h = self.fig.axes[self.active].plot(x, y, *args, **kwargs)
        if animate:
            self.artists.append(tuple(h))
        self.draw()

    def cone(self, obj, alpha, *args, **kwargs):
        """Draw small circle."""
        assert issubclass(
            obj.type, Vector3
        ), "Only Vector3-like instance could be used as cone axis."
        if "zorder" not in kwargs:
            kwargs["zorder"] = 5
        animate = kwargs.pop("animate", False)
        upper_style = False
        if isinstance(obj, Group):
            obj = obj.R
        azi, inc = obj.dd
        if obj.upper:
            inc = -inc
            upper_style = True
        x, y = self._cone(
            l2v(azi, inc),
            l2v(azi, inc - alpha),
            limit=180,
            res=int(sind(alpha) * 358 + 3),
            split=True,
        )
        h = self.fig.axes[self.active].plot(x, y, *args, **kwargs)
        if upper_style:
            for hl in h:
                hl.set_linestyle("--")
        if animate:
            self.artists.append(tuple(h))
        self.draw()

    def pair(self, obj, *arg, **kwargs):
        """Draw  Pair as great circle with small point."""
        assert obj.type is Pair, "Only Pair type instance could be used."
        animate = kwargs.pop("animate", False)
        h1 = self.plane(obj.fol, *arg, **kwargs)
        x, y = l2xy(*obj.lin.dd)
        h2 = self.fig.axes[self.active].scatter(x, y, color="k", s=5, zorder=6)
        if animate:
            self.artists.append(tuple(h1 + h2))
        self.draw()

    def fault(self, obj, *arg, **kwargs):
        """Draw a fault-and-striae as in Angelier plot"""
        assert obj.type is Fault, "Only Fault type instance could be used."
        animate = kwargs.get("animate", False)
        self.plane(obj.fol, *arg, **kwargs)
        x, y, u, v = self._arrow(obj.lin, sense=obj.sense)
        a = self.fig.axes[self.active].quiver(
            x, y, u, v, width=2, headwidth=5, zorder=6, pivot="mid", units="dots"
        )
        p = self.fig.axes[self.active].scatter(x, y, color="k", s=5, zorder=6)
        if animate:
            self.artists[-1] = self.artists[-1] + tuple(a + p)
        self.draw()

    def hoeppner(self, obj, *arg, **kwargs):
        """Draw a fault-and-striae as in tangent lineation plot - Hoeppner plot."""
        assert obj.type is Fault, "Only Fault type instance could be used."
        animate = kwargs.get("animate", False)
        self.pole(obj.fol, *arg, **kwargs)
        x, y, u, v = self._arrow(obj.fvec.aslin, dir_lin=obj.lin, sense=obj.sense)
        a = self.fig.axes[self.active].quiver(
            x, y, u, v, width=2, headwidth=5, zorder=6, pivot="mid", units="dots"
        )
        p = self.fig.axes[self.active].scatter(x, y, color="k", s=5, zorder=6)
        if animate:
            self.artists[-1] = self.artists[-1] + tuple(a + p)
        self.draw()

    def tensor(self, obj, *arg, **kwargs):
        """Draw tensor pricipal planes as great circles."""
        eigenfols = kwargs.pop("eigenfols", True)
        eigenlins = kwargs.pop("eigenlins", False)
        if eigenfols:
            self.plane(obj.eigenfols[0], label=obj.name + "-E1", **kwargs)
            self.plane(obj.eigenfols[1], label=obj.name + "-E2", **kwargs)
            self.plane(obj.eigenfols[2], label=obj.name + "-E3", **kwargs)
        if eigenlins:
            self.line(obj.eigenlins[0], label=obj.name + "-E1", **kwargs)
            self.line(obj.eigenlins[1], label=obj.name + "-E2", **kwargs)
            self.line(obj.eigenlins[2], label=obj.name + "-E3", **kwargs)

    def contourf(self, obj, *args, **kwargs):
        """Plot filled contours."""
        clines = kwargs.pop("clines", True)
        legend = kwargs.pop("legend", False)
        if "cmap" not in kwargs and "colors" not in kwargs:
            kwargs["cmap"] = "Greys"
        if "zorder" not in kwargs:
            kwargs["zorder"] = 1
        if isinstance(obj, StereoGrid):
            d = obj
        else:
            d = StereoGrid(obj, **kwargs)
            # clean kwargs from StereoGrid keywords
            for att in ["grid", "npoints", "sigma", "method", "trim"]:
                kwargs.pop(att, None)
        if "levels" not in kwargs:
            if len(args) == 0:
                args = (6,)
            if isinstance(args[0], int):
                mn = d.values.min()
                mx = d.values.max()
                levels = np.linspace(mn, mx, args[0])
                levels[-1] += 1e-8
                args = (levels,)
        cs = self.fig.axes[self.active].tricontourf(d.triang, d.values, *args, **kwargs)
        if clines:
            kwargs["cmap"] = None
            kwargs["colors"] = "k"
            self.fig.axes[self.active].tricontour(d.triang, d.values, *args, **kwargs)
        if legend:
            if self.ncols > 1:
                ab = self.fig.axes[self.active].get_position().bounds
                cbaxes = self.fig.add_axes(
                    [
                        ab[0] + self.cbpad * ab[2],
                        0.1,
                        (1 - 2 * self.cbpad) * ab[2],
                        0.03,
                    ]
                )
                self.fig.colorbar(cs, cax=cbaxes, orientation="horizontal")
                # add horizontal, calculate positions (divide bars and spaces)
            else:
                ab = self.fig.axes[self.active].get_position().bounds
                cbaxes = self.fig.add_axes(
                    [
                        0.1,
                        ab[1] + self.cbpad * ab[3],
                        0.03,
                        (1 - 2 * self.cbpad) * ab[3],
                    ]
                )
                self.fig.colorbar(cs, cax=cbaxes)
        self.draw()

    def contour(self, obj, *args, **kwargs):
        """Plot contour lines."""
        legend = kwargs.pop("legend", False)
        if "cmap" not in kwargs and "colors" not in kwargs:
            kwargs["cmap"] = "Greys"
        if "zorder" not in kwargs:
            kwargs["zorder"] = 1
        if isinstance(obj, StereoGrid):
            d = obj
        else:
            d = StereoGrid(obj, **kwargs)
            # clean kwargs from StereoGrid keywords
            for att in ["grid", "npoints", "sigma", "method", "trim"]:
                kwargs.pop(att, None)
        if "levels" not in kwargs:
            if len(args) == 0:
                args = (6,)
            if isinstance(args[0], int):
                mn = d.values.min()
                mx = d.values.max()
                levels = np.linspace(mn, mx, args[0])
                levels[-1] += 1e-8
                args = (levels,)
        cs = self.fig.axes[self.active].tricontour(d.triang, d.values, *args, **kwargs)
        if legend:
            if self.ncols > 1:
                ab = self.fig.axes[self.active].get_position().bounds
                cbaxes = self.fig.add_axes(
                    [
                        ab[0] + self.cbpad * ab[2],
                        0.1,
                        (1 - 2 * self.cbpad) * ab[2],
                        0.03,
                    ]
                )
                self.fig.colorbar(cs, cax=cbaxes, orientation="horizontal")
                # add horizontal, calculate positions (divide bars and spaces)
            else:
                ab = self.fig.axes[self.active].get_position().bounds
                cbaxes = self.fig.add_axes(
                    [
                        0.1,
                        ab[1] + self.cbpad * ab[3],
                        0.03,
                        (1 - 2 * self.cbpad) * ab[3],
                    ]
                )
                self.fig.colorbar(cs, cax=cbaxes)
        self.draw()

    # def _add_colorbar(self, cs):
    #     divider = make_axes_locatable(self.fig.axes[self.active])
    #     cax = divider.append_axes("left", size="5%", pad=0.5)
    #     plt.colorbar(cs, cax=cax)
    #     # modify tick labels
    #     # cb = plt.colorbar(cs, cax=cax)
    #     # lbl = [item.get_text()+'S' for item in cb.ax.get_yticklabels()]
    #     # lbl[lbl.index(next(l for l in lbl if l.startswith('0')))] = 'E'
    #     # cb.set_ticklabels(lbl)

    def axtitle(self, title):
        """Add title to active axes."""
        self._axtitle[self.active] = self.fig.axes[self.active].set_title(title)
        self._axtitle[self.active].set_y(-0.09)

    def title(self, title=""):
        """Set figure title."""
        self._title_text = title
        self._title = self.fig.suptitle(self._title_text)

    def show(self):
        """Call matplotlib show."""
        plt.show()

    def animate(self, **kwargs):
        """Return artist animation."""
        blit = kwargs.pop("blit", True)
        return animation.ArtistAnimation(self.fig, self.artists, blit=blit, **kwargs)

    def savefig(self, filename="apsg_stereonet.pdf", **kwargs):
        """Save figure to file."""
        self.draw()
        if not self.closed:  # check if figure exists
            bea_candidates = (self._lgd, self._title) + tuple(self._axtitle)
            bea = [art for art in bea_candidates if art is not None]
            self.fig.savefig(filename, bbox_extra_artists=bea, **kwargs)

    def format_coord(self, x, y):
        if np.hypot(x, y) > 1:
            return ""
        else:
            v = Vector3(*getldd(x, y))
            return repr(v.asfol) + " " + repr(v.aslin)

    def hover(self, event):
        vis = self.annot[self.active].get_visible()
        if event.inaxes == self.fig.axes[self.active]:
            for collection, labels in zip(self.artist_collection, self.artist_labels):
                cont, ind = collection.contains(event)
                if cont:
                    self.annot[self.active].xy = collection.get_offsets()[ind["ind"][0]]
                    text = " ".join([labels[n] for n in ind["ind"]])
                    self.annot[self.active].set_text(text)
                    self.annot[self.active].set_visible(True)
                    self.fig.canvas.draw_idle()
                else:
                    if vis:
                        self.annot[self.active].set_visible(False)
                        self.fig.canvas.draw_idle()


class StereoNetJK(object):

    """
    API to Joe Kington mplstereonet. Need maintanaince.
    """

    def __init__(self, *args, **kwargs):
        _, self._ax = mplstereonet.subplots(*args, **kwargs)
        self._grid_state = False
        self._cax = None
        self._lgd = None

    def draw(self):
        h, lbls = self._ax.get_legend_handles_labels()
        if h:
            self._lgd = self._ax.legend(
                h,
                lbls,
                bbox_to_anchor=(1.12, 1),
                loc=2,
                borderaxespad=0.0,
                numpoints=1,
                scatterpoints=1,
            )
            plt.subplots_adjust(right=0.75)
        else:
            plt.subplots_adjust(right=0.9)
        plt.draw()

    def cla(self):
        self._ax.cla()
        self._ax.grid(self._grid_state)
        self._cax = None
        self._lgd = None
        self.draw()

    def grid(self, state=True):
        self._ax.grid(state)
        self._grid_state = state
        self.draw()

    def plane(self, obj, *args, **kwargs):
        assert obj.type is Fol, "Only Fol type instance could be plotted as plane."
        strike, dip = obj.rhr
        self._ax.plane(strike, dip, *args, **kwargs)
        self.draw()

    def pole(self, obj, *args, **kwargs):
        assert obj.type is Fol, "Only Fol type instance could be plotted as pole."
        strike, dip = obj.rhr
        self._ax.pole(strike, dip, *args, **kwargs)
        self.draw()

    def rake(self, obj, rake_angle, *args, **kwargs):
        assert obj.type is Fol, "Only Fol type instance could be used with rake."
        strike, dip = obj.rhr
        self._ax.rake(strike, dip, rake_angle, *args, **kwargs)
        self.draw()

    def line(self, obj, *args, **kwargs):
        assert obj.type is Lin, "Only Lin type instance could be plotted as line."
        bearing, plunge = obj.dd
        self._ax.line(plunge, bearing, *args, **kwargs)
        self.draw()

    def arrow(self, obj, sense, *args, **kwargs):
        assert obj.type is Lin, "Only Lin type instance could be plotted as quiver."
        bearing, plunge = obj.dd
        xx, yy = mplstereonet.line(plunge, bearing)
        xx1, yy1 = mplstereonet.line(plunge - 5, bearing)
        for x, y, x1, y1 in zip(xx, yy, xx1, yy1):
            self._ax.arrow(x, y, sense * (x1 - x), sense * (y1 - y))
        self.draw()

    def cone(self, obj, angle, segments=100, bidirectional=True, **kwargs):
        assert obj.type is Lin, "Only Lin type instance could be used as cone axis."
        bearing, plunge = obj.dd
        self._ax.cone(
            plunge,
            bearing,
            angle,
            segments=segments,
            bidirectional=bidirectional,
            **kwargs,
        )
        self.draw()

    def density_contour(self, group, *args, **kwargs):
        assert type(group) is Group, "Only Group could be used for contouring."
        if group.type is Lin:
            bearings, plunges = group.dd
            kwargs["measurement"] = "lines"
            self._cax = self._ax.density_contour(plunges, bearings, *args, **kwargs)
            plt.draw()
        elif group.type is Fol:
            strikes, dips = group.rhr
            kwargs["measurement"] = "poles"
            self._cax = self._ax.density_contour(strikes, dips, *args, **kwargs)
            plt.draw()
        else:
            raise "Only Fol or Lin type Group is allowed."

    def density_contourf(self, group, *args, **kwargs):
        assert type(group) is Group, "Only Group could be used for contouring."
        if group.type is Lin:
            bearings, plunges = group.dd
            kwargs["measurement"] = "lines"
            self._cax = self._ax.density_contourf(plunges, bearings, *args, **kwargs)
            plt.draw()
        elif group.type is Fol:
            strikes, dips = group.rhr
            kwargs["measurement"] = "poles"
            self._cax = self._ax.density_contourf(strikes, dips, *args, **kwargs)
            plt.draw()
        else:
            raise "Only Fol or Lin type Group is allowed."

    def colorbar(self):
        if self._cax is not None:
            cbaxes = self._ax.figure.add_axes([0.015, 0.2, 0.02, 0.6])
            plt.colorbar(self._cax, cax=cbaxes)

    def savefig(self, filename="stereonet.pdf", **kwargs):
        if self._lgd is None:
            self._ax.figure.savefig(filename, **kwargs)
        else:
            self._ax.figure.savefig(
                filename, bbox_extra_artists=(self._lgd,), bbox_inches="tight", **kwargs
            )

    def show(self):
        plt.show()
