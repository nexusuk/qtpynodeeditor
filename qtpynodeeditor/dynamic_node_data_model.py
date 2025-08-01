"""
Dynamic Node Data Model

This module provides a NodeDataModel subclass that maintains a 'spare' input
connection that is always available to be connected to. Once a connection is
made, the input becomes a normal connection and a new spare connection is
created.
"""

import copy
from .node_data import NodeDataModel, NodeDataType
from .port import Port, PortType


class DynamicNodeDataModel(NodeDataModel, verify=False):
    """
    A NodeDataModel that dynamically manages input ports.

    This model maintains a 'spare' input connection that is always available
    to be connected to. Once a connection is made to the spare input, it
    becomes a normal input port and a new spare input port is automatically
    created.

    Use the standard NodeDataModel pattern - just define more input ports
    than you initially need:

    Example:
        class MyDynamicNode(DynamicNodeDataModel):
            num_ports = {'input': 5, 'output': 1}
            data_type = {
                'input': {
                    0: DecimalData.data_type,
                    1: DecimalData.data_type,
                    2: IntegerData.data_type,  # Different types allowed!
                    3: DecimalData.data_type,
                    4: DecimalData.data_type,
                },
                'output': {0: DecimalData.data_type}
            }

            def compute(self):
                # Process self.get_input_data(0), self.get_input_data(1), etc.
                pass
    """

    # Default configuration - subclasses should override these
    num_ports = {'input': 5, 'output': 1}
    
    # Port type configuration for mixed static/dynamic ports
    static_input_ports = None    # e.g., range(0, 3) for ports 0,1,2 as static
    dynamic_input_ports = None   # e.g., range(3, 8) for ports 3,4,5,6,7 as dynamic

    def __init_subclass__(cls, **kwargs):
        """Override to ensure dynamic port visibility"""
        super().__init_subclass__(**kwargs)
        # Note: port_visible is now created per-instance in __init__ to avoid shared state

    def __init__(self, style=None, parent=None):
        # Auto-detect port ranges if not specified FIRST
        if hasattr(self, 'num_ports'):
            max_inputs = self.num_ports.get('input', 5)
            max_outputs = self.num_ports.get('output', 1)
            
            if self.static_input_ports is None and self.dynamic_input_ports is None:
                # Default behavior: all ports are dynamic
                self.static_input_ports = range(0, 0)  # Empty range
                self.dynamic_input_ports = range(0, max_inputs)
            elif self.static_input_ports is None:
                self.static_input_ports = range(0, 0)  # Empty range
            elif self.dynamic_input_ports is None:
                self.dynamic_input_ports = range(0, 0)  # Empty range

        # Initialize tracking variables - set spare to first dynamic port
        self._active_input_count = 0
        self._spare_input_index = min(self.dynamic_input_ports) if self.dynamic_input_ports else -1
        self._connected_inputs = set()
        self._disconnected_inputs = set()  # Track previously connected ports that are now disconnected
        self._input_data = {}

        # Create port_visible dictionary - start with all input ports hidden
        self.port_visible = {
            'input': {i: False for i in range(max_inputs)},
            'output': {i: True for i in range(max_outputs)}  # Output ports always visible
        }

        # Copy port_caption and port_caption_visible to instance attributes to avoid sharing
        # Make deep copies to ensure complete isolation between instances
        if hasattr(self, 'port_caption'):
            self.port_caption = copy.deepcopy(self.port_caption)

        if hasattr(self, 'port_caption_visible'):
            self.port_caption_visible = copy.deepcopy(self.port_caption_visible)

        super().__init__(style=style, parent=parent)

        # Store original captions for restoration, but start with empty defaults
        self._original_port_caption = {}
        max_inputs = self.num_ports[PortType.input]

        # Copy any existing captions, but default to generic names
        # IMPORTANT: Save original captions BEFORE any "Connect here" overwrites them
        for i in range(max_inputs):
            # Use data type name if available, otherwise use existing port caption or generic name
            original_caption = None
            
            # First try to get data type name
            if hasattr(self, 'data_type') and PortType.input in self.data_type and i in self.data_type[PortType.input]:
                data_type = self.data_type[PortType.input][i]
                if data_type and hasattr(data_type, 'name'):
                    original_caption = data_type.name
            
            # Fall back to existing port caption or generic name
            if not original_caption:
                original_caption = self.port_caption[PortType.input].get(i, f"Input {i + 1}")
            
            self._original_port_caption[i] = original_caption

        # Update captions and visibility for dynamic behavior
        self._update_port_display()



    def _update_port_display(self):
        """Update port captions and visibility based on current state with visual ordering"""
        max_inputs = self.num_ports[PortType.input]
        
        # Hide all ports first
        for i in range(max_inputs):
            self.port_visible[PortType.input][i] = False
            self.port_caption[PortType.input][i] = ""
            self.port_caption_visible[PortType.input][i] = False
        
        # Static ports: always visible in their logical positions
        for logical_index in (self.static_input_ports or []):
            caption = self._original_port_caption.get(logical_index, f"Input {logical_index + 1}")
            self.port_caption[PortType.input][logical_index] = caption
            self.port_caption_visible[PortType.input][logical_index] = True
            self.port_visible[PortType.input][logical_index] = True
        
        # Dynamic ports: make visible based on visual ordering
        visual_order = self.get_visual_port_ordering()
        for logical_index in visual_order:
            if self.is_dynamic_port(logical_index):
                if logical_index == self._spare_input_index and self._spare_input_index >= 0:
                    # Spare port - special caption
                    self.port_caption[PortType.input][logical_index] = "Connect here"
                    self.port_caption_visible[PortType.input][logical_index] = True
                else:
                    # Connected or disconnected dynamic port
                    caption = self._original_port_caption.get(logical_index, f"Input {logical_index + 1}")
                    self.port_caption[PortType.input][logical_index] = caption
                    self.port_caption_visible[PortType.input][logical_index] = True
                
                self.port_visible[PortType.input][logical_index] = True

    def set_in_data(self, node_data, port: Port):
        """Handle input data and manage spare port logic"""
        port_index = port.index

        # Store/remove input data
        if node_data is not None:
            self._input_data[port_index] = node_data
        else:
            self._input_data.pop(port_index, None)

        # Process the input data (subclasses can override)
        self.process_input(node_data, port_index)

    def input_connection_created(self, connection):
        """Called when an input connection is created with support for static/dynamic ports"""
        port_index = connection.get_port_index(PortType.input)
        max_inputs = self.num_ports[PortType.input]

        # Static ports: use standard connection handling
        if self.is_static_port(port_index):
            super().input_connection_created(connection)
            return

        # Dynamic ports: validate visibility and apply packing logic
        if not self.is_dynamic_port(port_index):
            # Port is neither static nor dynamic - shouldn't happen, but handle gracefully
            super().input_connection_created(connection)
            return

        # Validate that the port is visible - if not, reject the connection
        if not self.can_connect_to_port(PortType.input, port_index):
            # Connection to hidden port - schedule removal after connection process completes
            from qtpy.QtCore import QTimer
            QTimer.singleShot(1, lambda: self._remove_invalid_connection(connection))
            return  # Don't process this connection further

        # If connecting to a disconnected dynamic port, move it back to connected
        if port_index in self._disconnected_inputs:
            self._disconnected_inputs.discard(port_index)
            self._connected_inputs.add(port_index)
            self._update_port_display()
            self.embedded_widget_size_updated.emit()
            self.data_updated.emit(0)

        # If this is the spare port, activate it
        elif port_index == self._spare_input_index:
            self._connected_inputs.add(port_index)
            self._active_input_count += 1

            # Move spare to next available dynamic slot that's not connected or disconnected
            for i in self.dynamic_input_ports:
                if i not in self._connected_inputs and i not in self._disconnected_inputs:
                    self._spare_input_index = i
                    break
            else:
                # All dynamic ports are now connected or disconnected, no more spare port
                self._spare_input_index = -1  # No spare port available

            # Update display and signal changes
            self._update_port_display()
            self.embedded_widget_size_updated.emit()
            self.data_updated.emit(0)

        # Call parent implementation
        super().input_connection_created(connection)

    def input_connection_deleted(self, connection):
        """Called when an input connection is deleted with support for static/dynamic ports"""
        port_index = connection.get_port_index(PortType.input)

        # Static ports: use standard connection handling
        if self.is_static_port(port_index):
            super().input_connection_deleted(connection)
            return

        # Dynamic ports: apply packing logic
        if not self.is_dynamic_port(port_index):
            # Port is neither static nor dynamic - shouldn't happen, but handle gracefully
            super().input_connection_deleted(connection)
            return

        # If we're disconnecting from a previously active dynamic port
        if port_index in self._connected_inputs:
            self._connected_inputs.discard(port_index)
            # Add to disconnected inputs so it remains visible as grayed out
            self._disconnected_inputs.add(port_index)

            # If this was the last active port, move spare back
            if port_index == self._active_input_count - 1:
                self._active_input_count -= 1
                # Find the next available dynamic slot for spare (not connected and not disconnected)
                for i in self.dynamic_input_ports:
                    if i not in self._connected_inputs and i not in self._disconnected_inputs:
                        self._spare_input_index = i
                        break
                else:
                    # No available dynamic slots, disable spare
                    self._spare_input_index = -1

            # Always update display when a connection is deleted
            self._update_port_display()
            self.embedded_widget_size_updated.emit()
            self.data_updated.emit(0)

        # If we're disconnecting from the spare port (edge case)
        elif port_index == self._spare_input_index:
            # Add to disconnected inputs so it remains visible as grayed out
            self._disconnected_inputs.add(port_index)

            # Move spare to next available dynamic slot (spare shouldn't be same as disconnected slot)
            # Find the next available dynamic slot that's not connected or disconnected
            for i in self.dynamic_input_ports:
                if i not in self._connected_inputs and i not in self._disconnected_inputs:
                    self._spare_input_index = i
                    break
            else:
                # No available dynamic slots, disable spare
                self._spare_input_index = -1

            # Always update display when a connection is deleted
            self._update_port_display()
            self.embedded_widget_size_updated.emit()
            self.data_updated.emit(0)

        # Call parent implementation
        super().input_connection_deleted(connection)

    def process_input(self, node_data, port_index):
        """
        Process input data for a specific port.

        Override this method in subclasses to handle input processing.

        Parameters
        ----------
        node_data : NodeData or None
            The input data, or None if disconnecting
        port_index : int
            The index of the input port
        """
        pass

    def compute(self):
        """
        Compute the output based on current inputs.

        Override this method in subclasses to implement the actual computation.
        Should return the output NodeData.

        Returns
        -------
        NodeData or None
            The computed output data
        """
        return None

    def out_data(self, port_index):
        """Return output data for the specified port"""
        if port_index == 0:
            return self.compute()
        return None

    def get_input_data(self, port_index):
        """
        Get input data for a specific port.

        Parameters
        ----------
        port_index : int
            The index of the input port

        Returns
        -------
        NodeData or None
            The input data at the specified port
        """
        return self._input_data.get(port_index)

    def get_all_input_data(self):
        """
        Get all connected input data as a list.

        Returns
        -------
        list
            List of (port_index, input_data) tuples for connected ports
        """
        return [(i, data) for i, data in self._input_data.items() if data is not None]

    def get_active_input_data(self):
        """
        Get input data for all active ports (0 to active_input_count-1).

        Returns
        -------
        list
            List of input data, with None for unconnected ports
        """
        inputs = []
        for i in range(self._active_input_count):
            inputs.append(self.get_input_data(i))
        return inputs

    def is_spare_port(self, port_index):
        """Check if a port is the spare port"""
        return port_index == self._spare_input_index

    def is_connected_port(self, port_index):
        """Check if a port is connected"""
        return port_index in self._connected_inputs

    def is_disconnected_port(self, port_index):
        """Check if a port is disconnected (previously connected but now unconnected)"""
        return port_index in self._disconnected_inputs

    def can_connect_to_port(self, port_type, port_index):
        """
        Check if a connection can be made to the specified port.
        
        This method is used to prevent connections to hidden ports in DynamicNodeDataModel.
        
        Parameters
        ----------
        port_type : PortType
            The type of port (input/output)
        port_index : int
            The index of the port
            
        Returns
        -------
        bool
            True if connection is allowed, False otherwise
        """
        # For dynamic nodes, only allow connections to visible ports
        if port_type == PortType.input and hasattr(self, 'port_visible'):
            return self.port_visible.get(PortType.input, {}).get(port_index, True)
        
        # For output ports or non-dynamic behavior, allow connections
        return True

    def _remove_invalid_connection(self, connection):
        """Remove a connection that was made to a hidden port"""
        try:
            # Try multiple approaches to remove the connection
            
            # Approach 1: Try to get scene from connection's graphics object
            if hasattr(connection, 'graphics_object') and connection.graphics_object:
                scene = connection.graphics_object.scene()
                if scene and hasattr(scene, 'delete_connection'):
                    scene.delete_connection(connection)
                    return
            
            # Approach 2: Try to get scene through the nodes
            if hasattr(connection, 'get_nodes'):
                input_node, output_node = connection.get_nodes()
                if input_node and hasattr(input_node, 'scene') and input_node.scene:
                    scene = input_node.scene
                    if hasattr(scene, 'delete_connection'):
                        scene.delete_connection(connection)
                        return
                        
            # Approach 3: Try to access the scene through the model's parent
            if hasattr(self, 'parent') and self.parent():
                node = self.parent()
                if hasattr(node, 'scene') and node.scene:
                    scene = node.scene
                    if hasattr(scene, 'delete_connection'):
                        scene.delete_connection(connection)
                        return
                        
            # Approach 4: Try to disconnect the connection directly
            if hasattr(connection, 'clear'):
                connection.clear()
            
        except Exception:
            # If we can't remove it gracefully, silently ignore
            pass

    @property
    def active_input_count(self):
        """Number of currently active input ports"""
        return self._active_input_count

    @property
    def spare_input_index(self):
        """Index of the current spare input port"""
        return self._spare_input_index

    def is_static_port(self, port_index):
        """Check if a port is static (non-dynamic)"""
        return (self.static_input_ports and 
                port_index in self.static_input_ports)

    def is_dynamic_port(self, port_index):
        """Check if a port is dynamic"""
        return (self.dynamic_input_ports and 
                port_index in self.dynamic_input_ports)

    def get_visual_port_ordering(self):
        """
        Get the visual ordering of input ports for display.
        Returns list of logical indices in visual order (top to bottom).
        Static ports appear first, then packed dynamic ports.
        """
        visual_order = []
        
        # 1. Static ports first (always in logical order)
        if self.static_input_ports:
            visual_order.extend(sorted(self.static_input_ports))
        
        # 2. Dynamic ports in packed order
        if self.dynamic_input_ports:
            # Only consider dynamic port indices for packing logic
            dynamic_connected = [i for i in self._connected_inputs 
                               if i in self.dynamic_input_ports]
            dynamic_disconnected = [i for i in self._disconnected_inputs 
                                  if i in self.dynamic_input_ports]
            
            # Connected dynamic ports (sorted for consistency)
            visual_order.extend(sorted(dynamic_connected))
            
            # Spare dynamic port
            if (self._spare_input_index >= 0 and 
                self._spare_input_index in self.dynamic_input_ports):
                visual_order.append(self._spare_input_index)
            
            # Disconnected dynamic ports (sorted for consistency)
            visual_order.extend(sorted(dynamic_disconnected))
        
        return visual_order

    def logical_to_visual_index(self, logical_index):
        """Convert logical port index to visual position (0=top, 1=next, etc.)"""
        visual_order = self.get_visual_port_ordering()
        try:
            return visual_order.index(logical_index)
        except ValueError:
            return None  # Hidden/invalid port

    def visual_to_logical_index(self, visual_index):
        """Convert visual position to logical port index"""
        visual_order = self.get_visual_port_ordering()
        if 0 <= visual_index < len(visual_order):
            return visual_order[visual_index]
        return None

    def get_visual_port_count(self):
        """Get count of visible ports"""
        return len(self.get_visual_port_ordering())


    def save(self):
        """
        Save the dynamic node state including disconnected inputs.
        
        Returns
        -------
        dict
            Dictionary containing the node state including disconnected inputs
        """
        # Get the base class state
        state = super().save() if hasattr(super(), 'save') else {}
        
        # Add our dynamic node specific state
        state.update({
            'dynamic_node_state': {
                'active_input_count': self._active_input_count,
                'spare_input_index': self._spare_input_index,
                'connected_inputs': list(self._connected_inputs),
                'disconnected_inputs': list(self._disconnected_inputs),
            }
        })
        
        return state

    def restore(self, state):
        """
        Restore the dynamic node state including disconnected inputs.
        
        Parameters
        ----------
        state : dict
            Dictionary containing the node state
        """
        # Restore base class state first
        if hasattr(super(), 'restore'):
            super().restore(state)
        
        # Restore our dynamic node specific state
        if 'dynamic_node_state' in state:
            dynamic_state = state['dynamic_node_state']
            
            self._active_input_count = dynamic_state.get('active_input_count', 0)
            self._spare_input_index = dynamic_state.get('spare_input_index', 0)
            self._connected_inputs = set(dynamic_state.get('connected_inputs', []))
            self._disconnected_inputs = set(dynamic_state.get('disconnected_inputs', []))
            
            # Update the port display to reflect restored state
            self._update_port_display()
            self.embedded_widget_size_updated.emit()
            self.data_updated.emit(0)