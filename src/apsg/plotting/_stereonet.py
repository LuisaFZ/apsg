# -*- coding: utf-8 -*-

import sys
import warnings
import pickle

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.cbook as mcb
from matplotlib.patches import Circle
from scipy.stats import vonmises

from apsg.config import apsg_conf
from apsg.math._vector import Vector3
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
from apsg.feature._tensor import Ortensor3
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
        self.fig, self.ax = plt.subplots(figsize=apsg_conf["figsize"])
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
        h, labels = self.ax.get_legend_handles_labels()
        if h:
            print("Here")
            self.ax.legend(
                h,
                labels,
                bbox_to_anchor=(1.05, 1),
                prop={"size": 11},
                loc="upper left",
                borderaxespad=0,
                scatterpoints=1,
                numpoints=1,
            )
        self.fig.tight_layout()
        # show
        plt.show()

    ########################################
    # PLOTTING                             #
    ########################################

    # KWARGS PARSING ROUTINES #

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
        parsed["label"] = kwargs.get("label", "_linear")
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
        parsed["label"] = kwargs.get("label", "_planar")
        return parsed

    def __parse_default_scatter_kwargs(self, kwargs):
        parsed = {}
        parsed["alpha"] = kwargs.get("alpha", None)
        parsed["s"] = kwargs.get("s", None)
        parsed["c"] = kwargs.get("c", None)
        parsed["linewidths"] = kwargs.get("linewidths", 1.5)
        parsed["marker"] = kwargs.get("marker", None)
        parsed["cmap"] = kwargs.get("cmap", None)
        parsed["legend"] = kwargs.get("legend", False)
        parsed["num"] = kwargs.get("num", "auto")
        parsed["label"] = kwargs.get("label", "_scatter")
        return parsed

    def __parse_default_contourf_kwargs(self, kwargs):
        parsed = {}
        parsed["alpha"] = kwargs.get("alpha", 1)
        parsed["antialiased"] = kwargs.get("antialiased", True)
        parsed["cmap"] = kwargs.get("cmap", "Greys")
        parsed["levels"] = kwargs.get("levels", 6)
        parsed["colorbar"] = kwargs.get("colorbar", False)
        parsed["sigma"] = kwargs.get("sigma", None)
        parsed["trim"] = kwargs.get("trim", True)
        return parsed

    def __parse_line_args(self, args, kwargs):
        parsed = self.__parse_default_linear_kwargs(kwargs)
        if parsed["label"] is True:
            if len(args) == 1:
                parsed["label"] = args[0].label()
            else:
                parsed["label"] = f"Linear ({len(args)})"
        return parsed

    def __parse_scatter_sizes_args(self, args, kwargs):
        parsed = self.__parse_default_scatter_kwargs(kwargs)
        if parsed["label"] is True:
            if len(args) == 1:
                parsed["label"] = args[0].label()
            else:
                parsed["label"] = f"Scatter ({len(args)})"
        # add scalar arguments to kwargs as list
        parsed["s"] = [float(v) for v in np.atleast_1d(args[1])]
        return parsed

    def __parse_scatter_colors_args(self, args, kwargs):
        parsed = self.__parse_default_scatter_kwargs(kwargs)
        if parsed["label"] is True:
            if len(args) == 1:
                parsed["label"] = args[0].label()
            else:
                parsed["label"] = f"Scatter ({len(args)})"
        # add scalar arguments to kwargs as list
        parsed["c"] = [float(v) for v in np.atleast_1d(args[1])]
        return parsed

    def __parse_vector_args(self, args, kwargs):
        parsed = self.__parse_default_linear_kwargs(kwargs)
        if parsed["label"] is True:
            if len(args) == 1:
                parsed["label"] = args[0].label()
            else:
                parsed["label"] = f"Vector ({len(args)})"
        return parsed

    def __parse_great_circle_args(self, args, kwargs):
        parsed = self.__parse_default_planar_kwargs(kwargs)
        if parsed["label"] is True:
            if len(args) == 1:
                parsed["label"] = args[0].label()
            else:
                parsed["label"] = f"Planar ({len(args)})"
        return parsed

    def __parse_cone_args(self, args, kwargs):
        parsed = self.__parse_default_planar_kwargs(kwargs)
        if parsed["label"] is True:
            if len(args[0]) == 1:
                parsed["label"] = f"Cone {str(args[0])} ({args[1]})"
            else:
                parsed["label"] = f"Cones ({len(args[0])})"
        # add scalar arguments to kwargs as list
        parsed["angles"] = [float(v) for v in np.atleast_1d(args[1])]
        return parsed

    def __parse_contourf_args(self, args, kwargs):
        parsed = self.__parse_default_contourf_kwargs(kwargs)
        return parsed

    # ARGUMENTS VALIDATIONS #

    # all args vector3-like
    def __validate_vector_args(self, args):
        if args:
            if all([issubclass(type(arg), (Vector3, Vector3Set)) for arg in args]):
                return True
            if self.show_warnings:
                print("Arguments must be Vector3 or Vector3Set like objects.")
        return False

    # all args linear
    def __validate_linear_args(self, args):
        if args:
            if all([issubclass(type(arg), (Vector3, Vector3Set)) for arg in args]):
                return True
            if self.show_warnings:
                print("Arguments must be Vector3 or Vector3Set like objects.")
        return False

    # first linear second scalar
    def __validate_linear_scalar_args(self, args):
        if len(args) == 2:
            if issubclass(type(args[0]), Vector3) and len(args) == 2:
                return True
            elif all([issubclass(type(arg), (Vector3, Vector3Set)) for arg in args[0]]):
                if len(args[0]) == len(np.atleast_1d(args[1])):
                    return True
                else:
                    if self.show_warnings:
                        print("Second argument must have same length as first.")
                    return False
            if self.show_warnings:
                print(
                    "First argument must be Vector3 or Vector3Set like objects and second scalar of same shape."
                )
        return False

    # all planar
    def __validate_planar_args(self, args):
        if args:
            if all([issubclass(type(arg), (Foliation, FoliationSet)) for arg in args]):
                return True
            if self.show_warnings:
                print("Arguments must be Foliation or FoliationSet like objects.")
        return False

    # first vector sets
    def __validate_contourf_args(self, args):
        if args:
            if issubclass(type(args[0]), Vector3Set):
                return True
            if self.show_warnings:
                print("First argument must be Vector3Set like objects.")
        return False

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
            if len(args) > 1:
                parsed["label"] = f"Planar ({len(args)})"
            self.__add_artist("_line", args, kwargs)

    def _line(self, *args, **kwargs):
        x_lower, y_lower = self.proj.project_data(*np.vstack(args).T)
        x_upper, y_upper = self.proj.project_data(*(-np.vstack(args).T))
        handles = self.ax.plot(
            np.hstack((x_lower, x_upper)), np.hstack((y_lower, y_upper)), **kwargs
        )
        for h in handles:
            h.set_clip_path(self.primitive)

    # ----==== SCATTER SIZE ====---=

    def scatter_size(self, *args, **kwargs):
        """Plot linear feature(s) as point(s)"""
        if self.__validate_linear_scalar_args(args):
            kwargs = self.__parse_scatter_sizes_args(args, kwargs)
            self.__add_artist("_scatter", args[0], kwargs)

    def scatter_color(self, *args, **kwargs):
        """Plot linear feature(s) as point(s)"""
        if self.__validate_linear_scalar_args(args):
            kwargs = self.__parse_scatter_colors_args(args, kwargs)
            self.__add_artist("_scatter", args[0], kwargs)

    def _scatter(self, *args, **kwargs):
        legend = kwargs.pop("legend")
        num = kwargs.pop("num")
        if kwargs["s"] is not None:
            sizes = kwargs.pop("s")
            x_lower, y_lower, s_lower = self.proj.project_data(
                *np.vstack(args).T, clip_also=sizes
            )
            x_upper, y_upper, s_upper = self.proj.project_data(
                *(-np.vstack(args).T), clip_also=sizes
            )
            sc = self.ax.scatter(
                np.hstack((x_lower, x_upper)),
                np.hstack((y_lower, y_upper)),
                s=np.hstack((s_lower, s_upper)),
                **kwargs,
            )
            if legend:
                self.ax.legend(
                    *sc.legend_elements("sizes", num=num),
                    bbox_to_anchor=(1.05, 1),
                    prop={"size": 11},
                    loc="upper left",
                    borderaxespad=0,
                    scatterpoints=1,
                    numpoints=1,
                )
        elif kwargs["c"] is not None:
            colors = kwargs.pop("c")
            x_lower, y_lower, c_lower = self.proj.project_data(
                *np.vstack(args).T, clip_also=colors
            )
            x_upper, y_upper, c_upper = self.proj.project_data(
                *(-np.vstack(args).T), clip_also=colors
            )
            sc = self.ax.scatter(
                np.hstack((x_lower, x_upper)),
                np.hstack((y_lower, y_upper)),
                c=np.hstack((c_lower, c_upper)),
                **kwargs,
            )
            if legend:
                self.ax.legend(
                    *sc.legend_elements("colors", num=num),
                    bbox_to_anchor=(1.05, 1),
                    prop={"size": 11},
                    loc="upper left",
                    borderaxespad=0,
                    scatterpoints=1,
                    numpoints=1,
                )
        else:
            x_lower, y_lower, c_lower = self.proj.project_data(*np.vstack(args).T)
            x_upper, y_upper, c_upper = self.proj.project_data(*(-np.vstack(args).T))
            sc = self.ax.scatter(
                np.hstack((x_lower, x_upper)),
                np.hstack((y_lower, y_upper)),
                c=np.hstack((c_lower, c_upper)),
                **kwargs,
            )
        sc.set_clip_path(self.primitive)

    # ----==== VECTOR ====---=

    def vector(self, *args, **kwargs):
        """Plot vector feature(s) as point(s), filled on lower and open on upper hemisphere."""
        if self.__validate_vector_args(args):
            kwargs = self.__parse_vector_args(args, kwargs)
            self.__add_artist("_vector", args, kwargs)

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
        if self.__validate_planar_args(args):
            kwargs = self.__parse_great_circle_args(args, kwargs)
            self.__add_artist("_great_circle", args, kwargs)

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
        if self.__validate_linear_scalar_args(args):
            kwargs = self.__parse_cone_args(args, kwargs)
            # scalar arguments are stored in kwargs due tu serialization
            self.__add_artist("_cone", args[0], kwargs)

    def _cone(self, *args, **kwargs):
        X, Y = [], []
        # get scalar arguments from kwargs
        angles = kwargs.pop("angles")
        for axis, angle in zip(np.atleast_2d(args), angles):
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

    # ----==== CONTOURF ====---=

    def contourf(self, *args, **kwargs):
        if self.__validate_contourf_args(args):
            kwargs = self.__parse_contourf_args(args, kwargs)
            self.__add_artist("_contourf", args[0], kwargs)

    def _contourf(self, *args, **kwargs):
        sigma = kwargs.pop("sigma")
        trim = kwargs.pop("trim")
        self.stereogrid.calculate_density(args[0], sigma=sigma, trim=trim)
        dcgrid = np.asarray(self.stereogrid.grid).T
        X, Y = self.proj.project_data(*dcgrid, clip_inside=False)
        cf = self.ax.tricontourf(X, Y, self.stereogrid.values, **kwargs)
        for collection in cf.collections:
            collection.set_clip_path(self.primitive)
        if colorbar:
            self.fig.colorbar(cf, ax=self.ax, shrink=0.6)
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
        self.fig = plt.figure(figsize=kwargs.pop("figsize", apsg_conf["figsize"]))
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
        self.fig = plt.figure(figsize=kwargs.pop("figsize", apsg_conf["figsize"]))
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
            for ln in np.arange(0.1, 1, 0.1):
                self.triplot([ln, ln], [0, 1 - ln], [1 - ln, 0], "k:")
                self.triplot([0, 1 - ln], [ln, ln], [1 - ln, 0], "k:")
                self.triplot([0, 1 - ln], [1 - ln, 0], [ln, ln], "k:")

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
        if issubclass(type(obj), Vector3Set):
            obj = obj.ortensor()

        if not isinstance(obj, Ortensor3):
            raise TypeError("Argument must be Vector3Set or Ortensor3")

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
        self.fig = plt.figure(figsize=kwargs.pop("figsize", apsg_conf["figsize"]))
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
        if issubclass(type(obj), Vector3Set):
            obj = obj.ortensor()

        if not isinstance(obj, Ortensor3):
            raise TypeError("Argument must be Vector3Set or Ortensor3")

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
        self.fig = plt.figure(figsize=kwargs.pop("figsize", apsg_conf["figsize"]))
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
        if issubclass(type(obj), Vector3Set):
            obj = obj.ortensor()

        if not isinstance(obj, Ortensor3):
            raise TypeError("Argument must be Vector3Set or Ortensor3")

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
        self.fig = plt.figure(figsize=kwargs.pop("figsize", apsg_conf["figsize"]))
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
        if issubclass(type(obj), Vector3Set):
            obj = obj.ortensor()

        if not isinstance(obj, Ortensor3):
            raise TypeError("Argument must be Vector3Set or Ortensor3")

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
