# node.py
# import sys
from node_class import Node, NODE_INFO, MY_NODE_ID, MY_IP_ADDRESS

if __name__ == "__main__":
    # if len(sys.argv) != 2:
    #     print("Usage: python node.py <my_node_id>")
    #     sys.exit(1)

    node = Node(MY_NODE_ID, MY_IP_ADDRESS, NODE_INFO)
    node.start()