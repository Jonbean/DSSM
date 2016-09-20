import theano
import theano.tensor as T
import lasagne
import numpy as np

class DNNLiar(object):
    def __init__(self, INPUTS_SIZE, LAYER_UNITS):

        self.inputs_size = INPUTS_SIZE
        self.layer_units = LAYER_UNITS
        self.hidden_layers = []
        self.dropout_rate = 0.0

        print type(self.inputs_size)
        print type(self.layer_units[0])

        self.l_in = lasagne.layers.InputLayer(shape=(None, self.inputs_size * 2))
        self.hidden_layers.append(self.l_in)
        for i in range(len(self.layer_units)):
            self.hidden_layers.append(lasagne.layers.DenseLayer(self.hidden_layers[i], 
                                        num_units=self.layer_units[i],
                                        nonlinearity=lasagne.nonlinearities.tanh))


        self.output = lasagne.layers.DenseLayer(self.hidden_layers[-1], self.inputs_size)
        self.all_params = lasagne.layers.get_all_params(self.output)
