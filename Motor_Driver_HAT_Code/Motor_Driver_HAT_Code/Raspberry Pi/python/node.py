# node.py
import sys
from node_class import Node, NODE_INFO #MY_NODE_ID, MY_IP_ADDRESS

if __name__ == "__main__":
    # if len(sys.argv) != 2:
    #     print("Usage: python node.py <my_node_id>")
    #     sys.exit(1)
    MY_NODE_ID = int(sys.argv[1])
    MY_IP_ADDRESS = NODE_INFO[MY_NODE_ID]


    node = Node(MY_NODE_ID, MY_IP_ADDRESS, NODE_INFO)
    node.start()