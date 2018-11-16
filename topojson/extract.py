from .utils.dispatcher import methdispatch
import json
import copy
import geopandas
from shapely import geometry
import geojson
import logging


class _Extract:
    """
    decompose shapes into linestrings and track record in bookkeeping_geoms.
    """

    def __init__(self):
        # initation topology items
        self.bookkeeping_geoms = []
        self.linestrings = []
        self.geomcollection_counter = 0
        self.invalid_geoms = 0

    @methdispatch
    def serialize_geom_type(self, geom):
        """
        This function handles the different types that can occur within a geojson object.
        Each type is registerd as its own function and called when found, 
        if none of the types match the input geom the current function is
        executed. 

        The adoption of the dispatcher approach makes the usage of multiple if-else statements
        not needed, since the dispatcher redirects the `geom` input to the function which
        handles that partical geometry type.

        The following geometry types are registered:
        - shapely.geometry.LineString
        - shapely.geometry.MultiLineString
        - shapely.geometry.Polygon
        - shapely.geometry.MultiPolygon
        - shapely.geometry.Point
        - shapely.geometry.MultiPoint
        - shapely.geometry.GeometryCollection
        - geojson.Feature
        - geojson.FeatureCollection
        - geopandas.GeoDataFrame
        - geopandas.GeoSeries
        - dict

        Any non-registered geometry wil return as an error that cannot be mapped.
        """

        return print("error: {} cannot be mapped".format(geom))

    @serialize_geom_type.register(geometry.LineString)
    def extract_line(self, geom):
        """
        *geom* type is LineString instance.
        """

        idx_bk = len(self.bookkeeping_geoms)
        idx_ls = len(self.linestrings)
        # record index and store linestring geom
        self.bookkeeping_geoms.append([idx_ls])
        self.linestrings.append(geom)

        # track record in object as well
        obj = self.obj
        if "arcs" not in obj:
            obj["arcs"] = []

        obj["arcs"].append(idx_bk)
        obj.pop("coordinates", None)

    @serialize_geom_type.register(geometry.MultiLineString)
    def extract_multiline(self, geom):
        """
        *geom* type is MultiLineString instance. 
        """

        for line in geom:
            self.extract_line(line)

    @serialize_geom_type.register(geometry.Polygon)
    def extract_ring(self, geom):
        """
        *geom* type is Polygon instance.
        """

        idx_bk = len(self.bookkeeping_geoms)
        idx_ls = len(self.linestrings)

        boundary = geom.boundary
        # catch ring with holes
        if isinstance(boundary, geometry.MultiLineString):
            # record index as list of items
            # and store each linestring geom
            lst_idx = list(range(idx_ls, idx_ls + len(list(boundary))))
            self.bookkeeping_geoms.append(lst_idx)
            for ls in boundary:
                self.linestrings.append(ls)
        else:
            # record index and store single linestring geom
            self.bookkeeping_geoms.append([idx_ls])
            self.linestrings.append(boundary)

        # track record in object as well
        obj = self.obj
        if "arcs" not in obj:
            obj["arcs"] = []

        obj["arcs"].append(idx_bk)
        obj.pop("coordinates", None)

    @serialize_geom_type.register(geometry.MultiPolygon)
    def extract_multiring(self, geom):
        """
        *geom* type is MultiPolygon instance. 
        """

        for ring in geom:
            self.extract_ring(ring)

    @serialize_geom_type.register(geometry.MultiPoint)
    @serialize_geom_type.register(geometry.Point)
    def extract_point(self, geom):
        """
        *geom* type is Point or MultiPoint instance.
        coordinates are directly passed to "coordinates"
        """

        obj = self.obj
        if "arcs" not in obj:
            obj["arcs"] = obj["coordinates"]
        obj.pop("coordinates", None)

    @serialize_geom_type.register(geometry.GeometryCollection)
    def extract_geometrycollection(self, geom):
        """
        *geom* type is GeometryCollection instance.
        """

        obj = self.data[self.key]
        self.geomcollection_counter += 1
        self.records_collection = len(geom)

        # iterate over the parsed shape(geom)
        # the original data objects is set as self._obj
        # the following lines can catch a GeometryCollection untill two levels deep
        # improvements on this are welcome
        for idx, geom in enumerate(geom):
            # if geom is GeometryCollection, collect geometries within collection on right level
            if isinstance(geom, geometry.GeometryCollection):
                self.records_collection = len(geom)
                if self.geomcollection_counter == 1:
                    self.obj = obj["geometries"]
                    self.geom_level_1 = idx
                if self.geomcollection_counter == 2:
                    self.obj = obj["geometries"][self.geom_level_1]["geometries"]

            # geom is NOT a GeometryCollection, determine location within collection
            else:
                if self.geomcollection_counter == 1:
                    self.obj = obj["geometries"][idx]
                    # if last record in collection is parsed set collection counter one level up
                    if idx == self.records_collection - 1:
                        self.geomcollection_counter += -1
                if self.geomcollection_counter == 2:
                    self.obj = obj["geometries"][self.geom_level_1]["geometries"][idx]
                    # if last record in collection is parsed set collection counter one level up
                    if idx == self.records_collection - 1:
                        self.geomcollection_counter += -1

            # set type for next loop
            self.serialize_geom_type(geom)

    @serialize_geom_type.register(geojson.FeatureCollection)
    def extract_featurecollection(self, geom):
        """
        *geom* type is FeatureCollection instance.
        """

        # convert FeatureCollection into a dict of features
        obj = self.obj
        data = {}
        zfill_value = len(str(len(obj["features"])))

        # each Feature becomes a new GeometryCollection
        for idx, feature in enumerate(obj["features"]):
            # A GeoJSON Feature is mapped to a GeometryCollection
            feature["type"] = "GeometryCollection"
            feature["geometries"] = [feature["geometry"]]
            feature.pop("geometry", None)
            data["feature_{}".format(str(idx).zfill(zfill_value))] = feature

        # new data dictionary is created, throw the geometries back to main()
        self.worker(data)

    @serialize_geom_type.register(geojson.Feature)
    def extract_feature(self, geom):
        """
        *geom* type is Feature instance.        
        """

        obj = self.obj

        # A GeoJSON Feature is mapped to a GeometryCollection
        obj["type"] = "GeometryCollection"
        obj["geometries"] = [obj["geometry"]]
        obj.pop("geometry", None)

        geom = geometry.shape(obj)
        if not geom.is_valid:
            self.invalid_geoms += 1
            del self.data[self.key]
            return

        self.serialize_geom_type(geom)

    @serialize_geom_type.register(geopandas.GeoDataFrame)
    @serialize_geom_type.register(geopandas.GeoSeries)
    def extract_geopandas(self, geom):
        """
        *geom* type is GeoDataFrame/GeoSeries instance.        
        """

        self.obj = geom.__geo_interface__
        self.extract_featurecollection(self.obj)

    @serialize_geom_type.register(dict)
    def extract_dictionary(self, geom):
        """
        *geom* type is Dictionary instance.        
        """

        # iterate over the input dictionary or geojson object
        # use list since https://stackoverflow.com/a/11941855
        for key in list(self.data):
            # based on the geom type the right function is serialized
            self.key = key
            self.obj = self.data[self.key]

            # determine firstly if type of geom is a Shapely geometric object if not then
            # the object might be a geojson Feature or FeatureCollection
            # otherwise it is not a recognized object and it will be removed
            try:
                geom = geometry.shape(self.obj)
                # object can be mapped, but may not be valid. remove invalid objects and continue
                if not geom.is_valid:
                    self.invalid_geoms += 1
                    del self.data[self.key]
                    continue
            except ValueError:
                # object might be a geojson Feature or FeatureCollection
                geom = geojson.loads(geojson.dumps(self.obj))
            except TypeError:
                # object is not valid
                self.invalid_geoms += 1
                del self.data[self.key]
                continue

            # the geom object is recognized, lets serialize the geometric type.
            # this function redirects the geometric object based on its type to
            # an equivalent function. Adopting this approach avoids the usage of
            # multiple if-else statements.
            self.serialize_geom_type(geom)

            # reset geom collection counter and level
            self.geomcollection_counter = 0
            self.geom_level_1 = 0

    def worker(self, data):
        """"
        Extracts the linestrings from the specified hash of geometry objects.

        The extract function is the first step in the topology computation.
        The following sequence is adopted:
        1. extract
        2. join
        3. cut
        4. dedup

        Returns an object with two new properties:

        * linestrings - linestrings extracted from the hash, of the form [start, end], as shapely objects
        * bookkeeping_geoms - record array storing index numbers of linestrings used in each object.

        For each line or polygon geometry in the input hash, including nested
        geometries as in geometry collections, the `coordinates` array is replaced
        with an equivalent `"coordinates"` array that points to one of the 
        linestrings as indexed in `bookkeeping_geoms`.

        Points geometries are not collected within the new properties, but are placed directly
        into the `"coordinates"` array within each object.

        Developping Notes
        * maybe better to include serialization of string type instead of handling this in worker
        * serialize GeoDataFrame and GeoSeries type
        """

        self.data = data
        self.serialize_geom_type(data)

        # prepare to return object
        topo = {
            "type": "Topology",
            "linestrings": self.linestrings,
            "bookkeeping_geoms": self.bookkeeping_geoms,
            "objects": self.data,
        }

        # show the number of invalid geometries have been removed if any
        if self.invalid_geoms > 0:
            logging.warning(
                "removed {} invalid geometric object{}".format(
                    self.invalid_geoms, "" if self.invalid_geoms == 1 else "s"
                )
            )

        return topo


def _extracter(data):
    # since we move and replace data in the object, need a deepcopy to avoid changing the input-data
    try:
        data = copy.deepcopy(data)
    except:
        data = data.copy()
    Extract = _Extract()
    e = Extract.worker(data)
    return e
