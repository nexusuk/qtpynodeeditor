"""
Dynamic Node Data Model

This module provides a NodeDataModel subclass that maintains a 'spare' input
connection that is always available to be connected to. Once a connection is
made, the input becomes a normal connection and a new spare connection is
created.
"""

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

    def __init_subclass__(cls, **kwargs):
        """Override to ensure dynamic port visibility"""
        super().__init_subclass__(**kwargs)

        # Create a new port_visible attribute to control actual port rendering
        if hasattr(cls, 'num_ports'):
            max_inputs = cls.num_ports.get('input', 5)
            max_outputs = cls.num_ports.get('output', 1)

            # Create port_visible dictionary - start with all input ports hidden
            cls.port_visible = {
                'input': {i: False for i in range(max_inputs)},
                'output': {i: True for i in range(max_outputs)}  # Output ports always visible
            }

    def __init__(self, style=None, parent=None):
        # Initialize tracking variables
        self._active_input_count = 0
        self._spare_input_index = 0
        self._connected_inputs = set()
        self._disconnected_inputs = set()  # Track previously connected ports that are now disconnected
        self._input_data = {}

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
        """Update port captions and visibility based on current state"""
        max_inputs = self.num_ports[PortType.input]

        # Update captions and visibility
        for i in range(max_inputs):
            if i == self._spare_input_index and self._spare_input_index >= 0:
                # Spare port - special caption (check this first!)
                self.port_caption[PortType.input][i] = "Connect here"
                self.port_caption_visible[PortType.input][i] = True
                self.port_visible[PortType.input][i] = True

            elif i in self._connected_inputs:
                # Connected port - use original caption or default
                caption = self._original_port_caption.get(i, f"Input {i + 1}")
                self.port_caption[PortType.input][i] = caption
                self.port_caption_visible[PortType.input][i] = True
                self.port_visible[PortType.input][i] = True

            elif i in self._disconnected_inputs:
                # Disconnected port - show as grayed out but visible
                caption = self._original_port_caption.get(i, f"Input {i + 1}")
                self.port_caption[PortType.input][i] = caption
                self.port_caption_visible[PortType.input][i] = True
                self.port_visible[PortType.input][i] = True

            else:
                # Hidden port - completely invisible (no ellipse, no caption)
                self.port_caption[PortType.input][i] = ""
                self.port_caption_visible[PortType.input][i] = False
                self.port_visible[PortType.input][i] = False

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
        """Called when an input connection is created"""
        port_index = connection.get_port_index(PortType.input)
        max_inputs = self.num_ports[PortType.input]

        # If connecting to a disconnected port, move it back to connected
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

            # Move spare to next available slot that's not connected or disconnected
            for i in range(max_inputs):
                if i not in self._connected_inputs and i not in self._disconnected_inputs:
                    self._spare_input_index = i
                    break
            else:
                # All ports are now connected or disconnected, no more spare port
                self._spare_input_index = -1  # No spare port available

            # Update display and signal changes
            self._update_port_display()
            self.embedded_widget_size_updated.emit()
            self.data_updated.emit(0)

        # Call parent implementation
        super().input_connection_created(connection)

    def input_connection_deleted(self, connection):
        """Called when an input connection is deleted"""
        port_index = connection.get_port_index(PortType.input)

        # If we're disconnecting from a previously active port
        if port_index in self._connected_inputs:
            self._connected_inputs.discard(port_index)
            # Add to disconnected inputs so it remains visible as grayed out
            self._disconnected_inputs.add(port_index)

            # If this was the last active port, move spare back
            if port_index == self._active_input_count - 1:
                self._active_input_count -= 1
                # Find the next available slot for spare (not connected and not disconnected)
                max_inputs = self.num_ports[PortType.input]
                for i in range(max_inputs):
                    if i not in self._connected_inputs and i not in self._disconnected_inputs:
                        self._spare_input_index = i
                        break
                else:
                    # No available slots, disable spare
                    self._spare_input_index = -1

            # Always update display when a connection is deleted
            self._update_port_display()
            self.embedded_widget_size_updated.emit()
            self.data_updated.emit(0)

        # If we're disconnecting from the spare port (edge case)
        elif port_index == self._spare_input_index:
            # Add to disconnected inputs so it remains visible as grayed out
            self._disconnected_inputs.add(port_index)

            # Move spare to next available slot (spare shouldn't be same as disconnected slot)
            # Find the next available slot that's not connected or disconnected
            max_inputs = self.num_ports[PortType.input]
            for i in range(max_inputs):
                if i not in self._connected_inputs and i not in self._disconnected_inputs:
                    self._spare_input_index = i
                    break
            else:
                # No available slots, disable spare
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

    @property
    def active_input_count(self):
        """Number of currently active input ports"""
        return self._active_input_count

    @property
    def spare_input_index(self):
        """Index of the current spare input port"""
        return self._spare_input_index