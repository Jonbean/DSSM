import theano
import theano.tensor as The
import lasagne
import numpy as np

class BGRUEncoder(object):
    def __init__(self, LAYER_1_UNITS, dropout_rate = 0.0, wemb_trainable = 1):
        self.layer1_units = LAYER_1_UNITS
        self.wemb = None
        self.GRAD_CLIP = 10.
        self.dropout_rate = dropout_rate
        self.l_in = None
        self.l_mask = None
        self.output = None
        self.wemb_trainable = wemb_trainable

    def build_model(self, WordEmbedding_Init = None):

        self.wemb = WordEmbedding_Init

        #create symbolic representation of inputs, mask and target_value

        # l_in input shape ==> (n_batch, n_time_steps, n_features)
        # The number of feature dimensions is 1(index). 
        self.l_in = lasagne.layers.InputLayer(shape=(None, None, 1))

        # Masks input shape ==> (n_batch, n_time_steps)
        self.l_mask = lasagne.layers.InputLayer(shape=(None, None))

        #setting gates and cell parameters with specific nonlinearity functions

        # The embedding layers with retieve subtensor from word embedding matrix
        l_emb = lasagne.layers.EmbeddingLayer(self.l_in, input_size=self.wemb.get_value().shape[0], output_size=self.wemb.get_value().shape[1], W=self.wemb)
        if not self.wemb_trainable:
            l_emb.params[l_emb.W].remove('trainable')

        l_drop = lasagne.layers.DropoutLayer(l_emb, p = self.dropout_rate)
        #setting gates and cell parameters with specific nonlinearity functions
        # gate_parameters = lasagne.layers.recurrent.Gate(W_in=lasagne.init.Orthogonal(), 
        #                                                 W_hid=lasagne.init.Orthogonal(),
        #                                                 b=lasagne.init.Constant(0.))

        # cell_parameters = lasagne.layers.recurrent.Gate(W_in=lasagne.init.Orthogonal(), 
        #                                                 W_hid=lasagne.init.Orthogonal(),
        #                                                 # Setting W_cell to None denotes that no cell connection will be used. 
        #                                                 W_cell=None, 
        #                                                 b=lasagne.init.Constant(0.),
        #                                                 # By convention, the cell nonlinearity is tanh in an LSTM. 
        #                                                 nonlinearity=lasagne.nonlinearities.tanh)

        # The embedding layers with retieve subtensor from word embedding matrix

        # The LSTM layer should have the same mask input in order to avoid padding entries
        # l_lstm = lasagne.layers.recurrent.LSTMLayer(l_drop, 
        #                                             num_units=self.layer1_units,
        #                                             # We need to specify a separate input for masks
        #                                             mask_input=self.l_mask,
        #                                             # Here, we supply the gate parameters for each gate 
        #                                             ingate=gate_parameters, forgetgate=gate_parameters, 
        #                                             cell=cell_parameters, outgate=gate_parameters,
        #                                             # We'll learn the initialization and use gradient clipping 
        #                                             learn_init=True, grad_clipping=self.GRAD_CLIP
        #                                             )
        gate_parameters = lasagne.layers.recurrent.Gate(W_in=lasagne.init.Orthogonal(), 
                                                        W_hid=lasagne.init.Orthogonal(),
                                                        W_cell=None,
                                                        b=lasagne.init.Constant(0.001))
        hidden_parameter = lasagne.layers.recurrent.Gate(W_in=lasagne.init.Orthogonal(), 
                                                        W_hid=lasagne.init.Orthogonal(),
                                                        W_cell=None,
                                                        b=lasagne.init.Constant(0.001),
                                                        nonlinearity=lasagne.nonlinearities.tanh)

        # The LSTM layer should have the same mask input in order to avoid padding entries
        l_grurnn = lasagne.layers.recurrent.GRULayer(l_drop, num_units=self.layer1_units, resetgate=gate_parameters,
                                                    updategate=gate_parameters, hidden_update=hidden_parameter,
                                                    backwards=False,
                                                    learn_init=True, 
                                                    gradient_steps=-1, grad_clipping=self.GRAD_CLIP, 
                                                    precompute_input=True, mask_input=self.l_mask
                                                    )

        l_grurnn_back = lasagne.layers.recurrent.GRULayer(l_drop, num_units=self.layer1_units, resetgate=gate_parameters,
                                                    updategate=gate_parameters, hidden_update=hidden_parameter,
                                                    backwards=True,
                                                    learn_init=True, 
                                                    gradient_steps=-1, grad_clipping=self.GRAD_CLIP, 
                                                    precompute_input=True, mask_input=self.l_mask
                                                    )

        # The back directional LSTM layers

        # Do sum up of bidirectional LSTM results
        
        l_merge = lasagne.layers.ElemwiseSumLayer([l_grurnn, l_grurnn_back])
        #here we shuffle the dimension of the 3D output of matrix of l_lstm2 because
        #pooling layer's gonna collapse the trailling axes
        # l_shuffle = lasagne.layers.DimshuffleLayer(l_merge, (0,2,1))

        # l_pooling = lasagne.layers.GlobalPoolLayer(l_shuffle)

        l_out = l_merge
        # l_out = lasagne.layers.SliceLayer(l_grurnn, -1, 1)
        #we only record the output(shall we record each layer???)
        self.output = l_out
        self.all_params = lasagne.layers.get_all_params(l_out)
