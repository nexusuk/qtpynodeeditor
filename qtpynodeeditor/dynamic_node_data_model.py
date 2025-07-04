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
        self._input_data = {}
        
        super().__init__(style=style, parent=parent)
        
        # Store original captions for restoration, but start with empty defaults
        self._original_port_caption = {}
        max_inputs = self.num_ports[PortType.input]
        
        # Copy any existing captions, but default to generic names
        for i in range(max_inputs):
            self._original_port_caption[i] = self.port_caption[PortType.input].get(i, f"Input {i + 1}")
        
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
        
        # If this is the spare port, activate it
        if port_index == self._spare_input_index:
            self._connected_inputs.add(port_index)
            self._active_input_count += 1
            
            # Move spare to next available slot
            if self._active_input_count < max_inputs:
                self._spare_input_index = self._active_input_count
            else:
                # All ports are now connected, no more spare port
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
            
            # If this was the last active port, move spare back
            if port_index == self._active_input_count - 1:
                self._active_input_count -= 1
                self._spare_input_index = self._active_input_count
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
    
    @property
    def active_input_count(self):
        """Number of currently active input ports"""
        return self._active_input_count
    
    @property 
    def spare_input_index(self):
        """Index of the current spare input port"""
        return self._spare_input_index