"""
Given some set of map files for a region, generate a graph network of all roads.
"""
import argparse
import math
import networkx as nx
import os
import random
import typing as T
from networkx.algorithms.shortest_paths.generic import shortest_path
from xml.etree import ElementTree as ET

from src.util.distance import dist_range
from src.util.osm_dir import OSM_DIR


class Node:
    """
    Represents a point on the map that a route can go through.
    """

    def __init__(self, ref_id: str, latitude: float, longitude: float):
        self._ref_id = ref_id
        self._latitude = float(latitude)
        self._longitude = float(longitude)
        self._routes: T.Set[str] = set()

    def __repr__(self) -> str:
        return f"Node({self.ref_id} - {self.lat}, {self.lon})"

    def add_route(self, route: str) -> None:
        self._routes.add(route)

    @property
    def ref_id(self) -> str:
        return self._ref_id

    @property
    def latitude(self) -> float:
        return self._latitude

    @property
    def lat(self) -> float:
        return self._latitude

    @property
    def longitude(self) -> float:
        return self._longitude

    @property
    def lon(self) -> float:
        return self._longitude

    @property
    def routes(self) -> T.Set[str]:
        return self._routes


class Map:
    """
    Represents roads on a map.

    Generally want to null-initialize.
    """

    def __init__(self):
        self._map = nx.Graph()
        self._nodes: T.Dict[str, Node] = dict()

    def ingest_file(self, full_path: str) -> None:
        # read all nodes first into the map, keep a copy of them locally as well
        with open(full_path, 'rb') as outfile:
            tree = ET.parse(outfile)
        root = tree.getroot()
    
        # don't create nodes if we've already done it
        node_elements = root.findall('node')
        for node_element in node_elements:
            node_id = node_element.attrib["id"]
            if node_id in self._nodes:
                continue
            new_node = Node(
                ref_id=node_id,
                latitude=node_element.attrib['lat'],
                longitude=node_element.attrib['lon']
            )
            self._map.add_node(new_node)
            self._nodes[node_id] = new_node
    
        # for each way element, join all nodes and create a path
        way_elements = root.findall('way')
        for way_element in way_elements:

            # don't include ferrys
            is_ferry = False
            for tag in way_element.findall('tag'):
                if tag.attrib['k'] == "route" and tag.attrib['v'] == "ferry":
                    is_ferry = True
                    break

            if is_ferry:
                continue

            edges_with_data = []
            node_pairs: T.Iterable[T.Tuple[ET.Element, ET.Element]] = zip(way_element.findall('nd')[:-1], way_element.findall('nd')[1:])
            for e1, e2 in node_pairs:
                e1_id = e1.attrib['ref']
                e2_id = e2.attrib['ref']
                n1 = self._nodes[e1_id]
                n2 = self._nodes[e2_id]
                edges_with_data.append((n1, n2, dist_range(n1.lat, n1.lon, n2.lat, n2.lon)))
            self._map.add_weighted_edges_from(edges_with_data)

    @classmethod
    def create_from_osm_files(cls, *osm_files) -> "Map":
        map = Map()
        for osm_file in osm_files:
            map.ingest_file(osm_file)
        return map

    def prune_components(self, min_size: int) -> None:
        """
        Remove all components from the graph that have a minimum size less than specified.

        Nodes and edges should both be removed.
        """
        nodes_to_remove: T.Set[Node] = set()
        for component in nx.components.connected_components(self._map):
            if len(component) < min_size:
                nodes_to_remove.update(component)
        self._map.remove_nodes_from(nodes_to_remove)

    def connect_disjoint_or_prune(self, max_dist: float) -> None:
        """
        Draw a line between disconnected components, searching for the minimum distance.

        If the minimum distance exceeds the max_dist specification, drop the smaller component.
        """
        primary = None
        max_size = 0
        other_components = list(nx.components.connected_components(self._map))
        for component in other_components:
            if len(component) > max_size:
                max_size = len(component)
                primary = component

        # try to link primary to all other nodes
        # TODO: i'm sure there's a more clever way to do this but we don't need this to be
        # blazing fast -- taking a few seconds to load is fine
        other_components.remove(primary)
        for component in other_components:
            min_dist = float('inf')
            node_p = None  # primary node
            node_o = None  # other node
            for o in component:
                for p in primary:
                    o: Node = o
                    p: Node = p
                    dist = dist_range(o.lat, o.lon, p.lat, p.lon)
                    if dist < min_dist:
                        node_p = p
                        node_o = o
                        min_dist = dist
            if min_dist < max_dist:
                # connect the components at their closest points
                self._map.add_edge(node_p, node_o, weight=min_dist)
                print(f'Adding edge between {node_p}, {node_o} with dist {min_dist}')
            else:
                # remove the smaller component
                print(f'Removing smaller component, too far away: {min_dist}')
                self._map.remove_nodes_from(component)


    def get_node_from_id(self, ref_id: str) -> Node:
        return self._nodes[ref_id]

    def get_neighbors_of_node(self, ref_id: str):
        ref_node = self._nodes[ref_id]
        return self._map[ref_node]

    def get_closest_node_to_point(self, lat: float, lon: float) -> Node:
        """
        Return the closest graph node to some point.

        TODO: there's smart ways to do this like splitting nodes into cells. We can
        time this to see how long it takes for reasonably sized maps.
        """
        min_dist = float('inf')
        min_node = None
        for node in self._nodes.values():
            dist = dist_range(lat, lon, node.lat, node.lon)
            if dist < min_dist:
                min_dist = dist
                min_node = node
        return min_node

    def get_random_node(self) -> Node:
        return list(self._nodes.values())[random.randint(0, len(self._nodes) + 1)]

    def get_shortest_route_between_points(self, start_node: Node, end_node: Node) -> T.List[Node]:
        """
        Get a list of nodes that make up the shortest path between two nodes.
        """
        if start_node not in self._nodes.values():
            raise ValueError("Start node not in graph nodes")
        if end_node not in self._nodes.values():
            raise ValueError("End node not in graph nodes")

        try:
            return shortest_path(self._map, start_node, end_node, 'weight')
        except nx.NetworkXNoPath:
            return []

    @classmethod
    def read_from_cache(cls, filename: str) -> "Map":
        """Read a map file from cache"""
        graph: nx.Graph = nx.read_gpickle(filename)
        map = Map()
        map._map = graph
        map._nodes = {x.ref_id: x for x in graph.nodes}
        return map

    def write_to_cache(self, filename: str) -> None:
        """
        The graph should contain everything needed to load the Map object
        """
        nx.write_gpickle(self._map, filename)


def get_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("region", choices=os.listdir(OSM_DIR))
    parser.add_argument("--prune-disjoint", type=int, default=100, help="drop nodes in components smaller than this size")
    parser.add_argument("--connect-disjoint", type=float, default=0.001, help="connect components that are closer than this limit")
    cache_group = parser.add_mutually_exclusive_group()
    cache_group.add_argument("--write-to-cache", action="store_true")
    cache_group.add_argument("--read-from-cache", action="store_true")
    return parser


def main() -> None:
    parser = get_parser()
    args = parser.parse_args()
    region_dir = os.path.join(OSM_DIR, args.region)
    if args.read_from_cache:
        filename = os.path.join(OSM_DIR, args.region, "map.gpickle")
        print(f'Reading map from cache at {filename}')
        map = Map.read_from_cache(filename)
    else:
        print(f'Reading map directly.')
        map = Map.create_from_osm_files(*[
            os.path.join(region_dir, filename)
            for filename in os.listdir(region_dir)
            if filename.endswith('.osm')
        ])

    map.prune_components(args.prune_disjoint)
    map.connect_disjoint_or_prune(args.connect_disjoint)

    filename = os.path.join(OSM_DIR, args.region, "map.gpickle")
    if args.write_to_cache:
        print(f'Writing map to cache at {filename}')
        map.write_to_cache(filename)

    import IPython; IPython.embed()


if __name__ == "__main__":
    main()
