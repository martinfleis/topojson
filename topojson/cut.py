from shapely import geometry
from shapely.ops import split
from shapely.ops import linemerge
import itertools
import numpy as np
import copy

class _Cut:
    """
    cut shared paths and keep track of it
    """

    def __init__(self):
        # initation topology items
        self.duplicates = []
        pass       

    def index_array(self, parameter_list):
        # create numpy array from variable
        array_bk = np.array(list(itertools.zip_longest(*parameter_list, fillvalue=np.nan))).T
        return array_bk

    def flatten_and_index(self, slist):
        """
        function to create a flattened list of splitted linestrings, but make sure to
        create a numpy array for bookkeeping for thee numerical computation
        """
        # flatten
        segmntlist = list(itertools.chain(*slist))
        # create slice pairs
        segmnt_idx = list(itertools.accumulate([len(geom) for geom in slist]))
        slice_pair = [(segmnt_idx[idx - 1] if idx >= 1 else 0, current) for idx, current in enumerate(segmnt_idx)]
        # index array
        list_bk = [range(len(segmntlist))[s[0]:s[1]] for s in slice_pair]
        array_bk = self.index_array(list_bk)
        
        return segmntlist, array_bk  

    def list_from_array(self, array_bk):
        # convert to list after numpy computation is finished
        list_bk = [obj[~np.isnan(obj)].astype(int).tolist() for obj in array_bk]   
        return list_bk        
            
    def main(self, data):
        """
        Cut the linestrings given the junctions of shared paths.

        The cut function is the third step in the topology computation.
        The following sequence is adopted:
        1. extract
        2. join
        3. cut 
        4. dedup      
        """

        # split each feature given the intersections 
        mp = geometry.MultiPoint(data['junctions'])
        slist = []
        for ls in data['linestrings']:
            slines = split(ls, mp)
            slist.append(list(geometry.MultiLineString(slines)))        
        
        # flatten the splitted linestrings and create bookkeeping array
        segments_list, bk_array = self.flatten_and_index(slist)

        # find duplicates of splitted linestrings
        # first create list with all combinations of lines including index
        ls_idx = [pair for pair in enumerate(segments_list)]
        line_combs = list(itertools.combinations(ls_idx, 2))

        # iterate over line combinations
        for geoms in line_combs:
            i1 = geoms[0][0]
            g1 = geoms[0][1]

            i2 = geoms[1][0]
            g2 = geoms[1][1]

            # check if geometry are equal
            # being equal meaning the geometry object coincide with each other.
            # a rotated polygon or reversed linestring are both considered equal.
            if g1.equals(g2):
                idx_pop = i1 if len(g1.coords) <= len(g2.coords) else i2
                idx_keep = i1 if i2 == idx_pop else i2
                self.duplicates.append((idx_keep, idx_pop)) 
        
        # TODO: separate shared arcs from single used arcs
        # TODO: apply linemerge on the single used arcs (this avoids inclusion of rotation!)
        # TODO: etc
        data['duplicates'] = self.duplicates
        data['bookkkeeping_linestrings'] = self.list_from_array(bk_array)

        return data
    
    
def _cutter(data):
    data = copy.deepcopy(data)
    Cut = _Cut()
    c = Cut.main(data)
    return c
