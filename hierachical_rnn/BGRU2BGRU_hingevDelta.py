import theano
import theano.tensor as T
import lasagne
import numpy as np
import os
import time
import utils
import cPickle as pickle
import BGRU_Encoder
import sys
# from theano.printing import pydotprint



class Hierachi_RNN(object):
    def __init__(self, rnn_setting, dropout_rate, batchsize, wemb_size = None):
        # Initialize Theano Symbolic variable attributes
        self.story_input_variable = None
        self.story_mask = None
        self.story_nsent = 4

        self.ending_input_variable = None
        self.ending_mask = None

        self.neg_ending1_input_variable = None
        self.neg_ending1_mask = None

        self.doc_encoder = None
        self.query_encoder = None 

        self.doc_encode = None 
        self.pos_end_encode = None
        self.neg_end_encode = None

        self.cost_vec = None
        self.cost = None

        self.train_func = None
        self.compute_cost = None

        # Initialize data loading attributes
        self.wemb = None
        self.train_set_path = '../../data/pickles/train_index_corpus.pkl'
        self.val_set_path = '../../data/pickles/val_index_corpus.pkl'
        self.test_set_path = '../../data/pickles/test_index_corpus.pkl' 

        self.wemb_matrix_path = '../../data/pickles/index_wemb_matrix.pkl'
        self.rnn_units = int(rnn_setting)
        # self.mlp_units = [int(elem) for elem in mlp_setting.split('x')]
        self.dropout_rate = float(dropout_rate)
        self.batchsize = int(batchsize)
        # self.reasoning_depth = int(reasoning_depth)
        self.wemb_size = 300
        if wemb_size == None:
            self.random_init_wemb = False
        else:
            self.random_init_wemb = True
            self.wemb_size = int(wemb_size)

        self.train_story = None
        self.train_ending = None

        self.val_story = None
        self.val_ending1 = None 
        self.val_ending2 = None
        self.val_answer = None
        self.n_val = None

        self.test_story = None 
        self.test_ending1 = None
        self.test_ending2 = None
        self.test_answer = None
        self.n_test = None

        self.train_encodinglayer_vecs = []

        self.delta = 5.0

    def encoding_layer(self):


        assert len(self.reshaped_inputs_variables)==len(self.inputs_masks)
        for i in range(self.story_nsent+1):
            self.train_encodinglayer_vecs.append(lasagne.layers.get_output(self.encoder.output,
                                                        {self.encoder.l_in:self.reshaped_inputs_variables[i], 
                                                         self.encoder.l_mask:self.inputs_masks[i]},
                                                         deterministic = True))

            # self.test_encodinglayer_vecs.append(lasagne.layers.get_output(self.encoder.output,{self.encoder.l_in:self.reshaped_inputs_variables[i], 
            #                                              self.encoder.l_mask:self.inputs_masks[i]},deterministic = True))
           

    def batch_cosine(self, batch_vectors1, batch_vectors2):
        dot_prod = T.batched_dot(batch_vectors1, batch_vectors2)

        batch1sqr = batch_vectors1 ** 2
        batch2sqr = batch_vectors2 ** 2

        batch1_norm = (T.sqrt(batch1sqr.sum(axis = 1))).sum()
        batch2_norm = T.sqrt(batch2sqr.sum(axis = 1)).sum()

        batch_cosine_vec = dot_prod/(batch1_norm * batch2_norm)
        return batch_cosine_vec

    def model_constructor(self, wemb_size = None):
        self.inputs_variables = []
        self.inputs_masks = []
        self.reshaped_inputs_variables = []
        for i in range(self.story_nsent+1):
            self.inputs_variables.append(T.matrix('story'+str(i)+'_input', dtype='int64'))
            self.inputs_masks.append(T.matrix('story'+str(i)+'_mask', dtype=theano.config.floatX))
            batch_size, seqlen = self.inputs_variables[i].shape
            self.reshaped_inputs_variables.append(self.inputs_variables[i].reshape([batch_size, seqlen, 1]))

        #initialize neural network units
        self.encoder = BGRU_Encoder.BGRUEncoder(LAYER_1_UNITS = self.rnn_units, dropout_rate = self.dropout_rate)
        self.encoder.build_model(self.wemb)

        #build encoding layer
        self.encoding_layer()

        #build reasoning layers

        self.merge_ls = [T.reshape(tensor, (tensor.shape[0], 1, tensor.shape[1])) for tensor in self.train_encodinglayer_vecs[:-1]]

        encode_merge = T.concatenate(self.merge_ls, axis = 1)
        l_in = lasagne.layers.InputLayer(shape=(None, None, self.rnn_units))

        l_gru = lasagne.layers.recurrent.GRULayer(l_in, num_units=self.rnn_units, backwards=False,
                                                    learn_init=True, 
                                                    gradient_steps=-1,
                                                    precompute_input=True)

        l_gru_back = lasagne.layers.recurrent.GRULayer(l_in, num_units=self.rnn_units, backwards=True,
                                                    learn_init=True, 
                                                    gradient_steps=-1,
                                                    precompute_input=True)

        # Do sum up of bidirectional LSTM results
        l_out_right = lasagne.layers.SliceLayer(l_gru, -1, 1)
        l_out_left = lasagne.layers.SliceLayer(l_gru_back, -1, 1)
        l_sum = lasagne.layers.ElemwiseSumLayer([l_out_right, l_out_left])

        reasoner_result = lasagne.layers.get_output(l_sum, {l_in: encode_merge}, deterministic = True)
        reasoner_params = lasagne.layers.get_all_params(l_sum)

        l_story_in = lasagne.layers.InputLayer(shape=(self.batchsize, self.rnn_units))
        l_end_in = lasagne.layers.InputLayer(shape = (self.batchsize, self.rnn_units))

        # we cache the encoded result to pick the max score negative sample from them later
        l_concate = lasagne.layers.ConcatLayer([l_story_in, l_end_in], axis = 1)

        l_hid = lasagne.layers.DenseLayer(l_concate, num_units=1, nonlinearity=lasagne.nonlinearities.tanh)

        final_class_param = lasagne.layers.get_all_params(l_hid)

        self.test_score = []
        for i in range(self.batchsize - 1):
            self.test_score.append(lasagne.layers.get_output(l_hid, {l_story_in: reasoner_result, 
                                                                     l_end_in: T.roll(self.train_encodinglayer_vecs[-1], shift=(i+1), axis = 0)}))

        score_matrix = T.concatenate(self.test_score, axis = 1)
        max_score_vec = T.max(score_matrix, axis = 1)
        max_score_index_pre = T.argmax(score_matrix, axis = 1)

        #1. generate index shift
        index_shift = theano.shared(np.arange(self.batchsize) + 1)
        #2. generate index shifted list
        bf_clip = max_score_index_pre + index_shift

        #3. shift back indices beyond the max
        clip_ls = bf_clip.clip(a_min = self.batchsize-1, a_max = self.batchsize) - (self.batchsize - 1)*T.ones(shape=(self.batchsize))
        max_score_index = T.cast(bf_clip - self.batchsize * clip_ls, 'int32')

        p = 2
        self.delta = p * (1 - self.batch_cosine(self.train_encodinglayer_vecs[-1], self.train_encodinglayer_vecs[-1][max_score_index]))



        score1 = lasagne.layers.get_output(l_hid, {l_story_in: reasoner_result, 
                                                   l_end_in: self.train_encodinglayer_vecs[-1]})
        
        self.score1 = T.flatten(score1)
        # prob1 = lasagne.nonlinearities.sigmoid(score1)
        # prob2 = lasagne.nonlinearities.sigmoid(score2)

        # Construct symbolic cost function

        # cost1 = lasagne.objectives.binary_crossentropy(prob1, target1)
        # cost2 = lasagne.objectives.binary_crossentropy(prob2, target2)
        score_vec = T.clip(self.delta - self.score1 + max_score_vec, 0.0, float('inf'))
        self.cost = lasagne.objectives.aggregate(score_vec, mode='sum') 


        # Retrieve all parameters from the network
        all_params = self.encoder.all_params + reasoner_params + final_class_param

        all_updates = lasagne.updates.adam(self.cost, all_params, learning_rate=0.001)
        # all_updates = lasagne.updates.momentum(self.cost, all_params, learning_rate = 0.05, momentum=0.9)

        self.train_func = theano.function(self.inputs_variables + self.inputs_masks, 
                                        [self.cost, self.score1, max_score_vec], updates = all_updates)

        # test ending2
        end2 = T.matrix(name = "test_end2", dtype = 'int64')
        mask_end2 = T.matrix(name="test_mask2", dtype = theano.config.floatX)

        batch_size, seqlen = end2.shape
        end2_reshape = end2.reshape([batch_size, seqlen, 1])

        encoded_end2 = lasagne.layers.get_output(self.encoder.output, {self.encoder.l_in: end2_reshape, 
                                                                       self.encoder.l_mask:mask_end2},
                                                                       deterministic = True)
        self.score2 = lasagne.layers.get_output(l_hid, {l_story_in: reasoner_result, 
                                                   l_end_in: encoded_end2})

        self.prediction = theano.function(self.inputs_variables + self.inputs_masks + [end2, mask_end2],
                                         [score1, self.score2])
        # pydotprint(self.train_func, './computational_graph.png')

    def load_data(self):
        train_set = pickle.load(open(self.train_set_path))
        self.train_story = train_set[0]
        self.train_ending = train_set[1]

        val_set = pickle.load(open(self.val_set_path))

        self.val_story = val_set[0]
        self.val_ending1 = val_set[1]
        self.val_ending2 = val_set[2]
        self.val_answer = val_set[3]

        self.n_val = len(self.val_answer)

        test_set = pickle.load(open(self.test_set_path))
        self.test_story = test_set[0]
        self.test_ending1 = test_set[1]
        self.test_ending2 = test_set[2]
        self.test_answer = test_set[3]
        self.n_test = len(self.test_answer)

        if self.random_init_wemb:
            wemb = np.random.rand(28820 ,self.wemb_size)
            wemb = np.concatenate((np.zeros((1, self.wemb_size)), wemb), axis = 0)
            self.wemb = theano.shared(wemb).astype(theano.config.floatX)
        else:
            self.wemb = theano.shared(pickle.load(open(self.wemb_matrix_path))).astype(theano.config.floatX)

    def fake_load_data(self):
        self.train_story = []
        self.train_story.append(np.concatenate((np.random.randint(10, size = (50, 10)), 10+np.random.randint(10, size=(50,10))),axis=0).astype('int64'))
        self.train_story.append(np.ones((100, 10)).astype('int64'))
        self.train_story.append(np.ones((100, 10)).astype('int64'))
        self.train_story.append(np.ones((100, 10)).astype('int64'))
        self.train_story = np.asarray(self.train_story).reshape([100,4,10])

        self.train_ending = np.concatenate((2 * np.ones((50, 5)), np.ones((50, 5))), axis = 0)
        self.val_story = []
        self.val_story.append(np.random.randint(10, size = (100, 10)).astype('int64'))
        self.val_story.append(np.random.randint(10, size = (100, 10)).astype('int64'))
        self.val_story.append(np.random.randint(10, size = (100, 10)).astype('int64'))
        self.val_story.append(np.random.randint(10, size = (100, 10)).astype('int64'))

        self.val_ending1 = np.ones((100, 10)).astype('int64')
        self.val_ending2 = 2*np.ones((100, 10)).astype('int64')
        self.val_answer = np.zeros(100)
        self.n_val = self.val_answer.shape[0]

        self.test_story = []
        self.test_story.append(np.random.randint(20, size = (100, 10)).astype('int64'))
        self.test_story.append(np.random.randint(20, size = (100, 10)).astype('int64'))
        self.test_story.append(np.random.randint(20, size = (100, 10)).astype('int64'))
        self.test_story.append(np.random.randint(20, size = (100, 10)).astype('int64'))

        self.test_ending1 = np.ones((100, 10)).astype('int64')
        self.test_ending2 = 2*np.ones((100, 10)).astype('int64')
        self.test_answer = np.ones(100)
        self.n_test = self.test_answer.shape[0]


        self.wemb = theano.shared(np.random.rand(30, self.rnn_units)).astype(theano.config.floatX)


    def val_set_test(self):

        correct = 0.

        minibatch_n = 50
        max_batch_n = self.n_val / minibatch_n
        for i in range(max_batch_n):

            story_ls = [[self.val_story[index][j] for index in range(i*minibatch_n, (i+1)*minibatch_n)] for j in range(self.story_nsent)]
            story_matrix = [utils.padding(batch_sent) for batch_sent in story_ls]
            story_mask = [utils.mask_generator(batch_sent) for batch_sent in story_ls]

            ending1_ls = [self.val_ending1[index] for index in range(i*minibatch_n, (i+1)*minibatch_n)]
            ending1_matrix = utils.padding(ending1_ls)
            ending1_mask = utils.mask_generator(ending1_ls)


            ending2_ls = [self.val_ending2[index] for index in range(i*minibatch_n, (i+1)*minibatch_n)]
            ending2_matrix = utils.padding(ending2_ls)
            ending2_mask = utils.mask_generator(ending2_ls)

            score1, score2 = self.prediction(story_matrix[0], story_matrix[1], story_matrix[2], story_matrix[3], 
                                    ending1_matrix, story_mask[0], story_mask[1], story_mask[2],
                                    story_mask[3], ending1_mask, ending2_matrix, ending2_mask)

            # Answer denotes the index of the anwer
            prediction = np.argmax(np.concatenate((score1, score2), axis=1), axis=1)
            correct_vec = prediction - self.val_answer[i*minibatch_n:(i+1)*minibatch_n]
            print correct_vec
            correct += minibatch_n - (abs(correct_vec)).sum()
            print correct

        for k in range(minibatch_n * max_batch_n, self.n_val):
            story = [np.asarray(sent, dtype='int64').reshape((1,-1)) for sent in self.val_story[k]]
            story_mask = [np.ones((1,len(self.val_story[k][j]))) for j in range(4)]

            ending1 = np.asarray(self.val_ending1[k], dtype='int64').reshape((1,-1))
            ending1_mask = np.ones((1,len(self.val_ending1[k])))

            ending2 = np.asarray(self.val_ending2[k], dtype='int64').reshape((1,-1))
            ending2_mask = np.ones((1, len(self.val_ending2[k])))

            score1, score2 = self.prediction(story[0], story[1], story[2], story[3], 
                                    ending1, story_mask[0], story_mask[1], story_mask[2],
                                    story_mask[3], ending1_mask, ending2, ending2_mask)
            # Answer denotes the index of the anwer
            prediction = np.argmax(np.concatenate((score1, score2), axis=1))

            if prediction == self.val_answer[k]:
                correct += 1.    
        print self.n_val
        return correct/self.n_val

    def test_set_test(self):
        correct = 0.

        minibatch_n = 50
        max_batch_n = self.n_test / minibatch_n
        for i in range(max_batch_n):

            story_ls = [[self.test_story[index][j] for index in range(i*minibatch_n, (i+1)*minibatch_n)] for j in range(self.story_nsent)]
            story_matrix = [utils.padding(batch_sent) for batch_sent in story_ls]
            story_mask = [utils.mask_generator(batch_sent) for batch_sent in story_ls]

            ending1_ls = [self.test_ending1[index] for index in range(i*minibatch_n, (i+1)*minibatch_n)]
            ending1_matrix = utils.padding(ending1_ls)
            ending1_mask = utils.mask_generator(ending1_ls)


            ending2_ls = [self.test_ending2[index] for index in range(i*minibatch_n, (i+1)*minibatch_n)]
            ending2_matrix = utils.padding(ending2_ls)
            ending2_mask = utils.mask_generator(ending2_ls)

            score1, score2 = self.prediction(story_matrix[0], story_matrix[1], story_matrix[2], story_matrix[3], 
                                    ending1_matrix, story_mask[0], story_mask[1], story_mask[2],
                                    story_mask[3], ending1_mask, ending2_matrix, ending2_mask)

            # Answer denotes the index of the anwer
            prediction = np.argmax(np.concatenate((score1, score2), axis=1), axis=1)
            correct_vec = prediction - self.test_answer[i*minibatch_n:(i+1)*minibatch_n]
            correct += minibatch_n - (abs(correct_vec)).sum()

        for k in range(minibatch_n * max_batch_n, self.n_test):
            story = [np.asarray(sent, dtype='int64').reshape((1,-1)) for sent in self.test_story[k]]
            story_mask = [np.ones((1,len(self.test_story[k][j]))) for j in range(4)]

            ending1 = np.asarray(self.test_ending1[k], dtype='int64').reshape((1,-1))
            ending1_mask = np.ones((1,len(self.test_ending1[k])))

            ending2 = np.asarray(self.test_ending2[k], dtype='int64').reshape((1,-1))
            ending2_mask = np.ones((1, len(self.test_ending2[k])))

            score1, score2 = self.prediction(story[0], story[1], story[2], story[3], 
                                    ending1, story_mask[0], story_mask[1], story_mask[2],
                                    story_mask[3], ending1_mask, ending2, ending2_mask)
            # Answer denotes the index of the anwer
            prediction = np.argmax(np.concatenate((score1, score2), axis=1))

            if prediction == self.test_answer[k]:
                correct += 1.            


        return correct/self.n_test


    def saving_model(self, val_or_test, accuracy):
        reason_params_value = lasagne.layers.get_all_param_values(self.reason_layer.output)
        classif_params_value = lasagne.layers.get_all_param_values(self.classify_layer.output)

        if val_or_test == 'val':
            pickle.dump((reason_params_value, classif_params_value, accuracy), 
                        open(self.best_val_model_save_path, 'wb'))
        else:
            pickle.dump((reason_params_value, classif_params_value, accuracy), 
                        open(self.best_test_model_save_path, 'wb'))            

    def reload_model(self, val_or_test):
        if val_or_test == 'val': 

            reason_params, classif_params, accuracy = pickle.load(open(self.best_val_model_save_path))
            lasagne.layers.set_all_param_values(self.reason_layer.output, reason_params)
            lasagne.layers.set_all_param_values(self.classify_layer.output, classif_params)

            print "This model has ", accuracy * 100, "%  accuracy on valid set" 
        else:
            reason_params, classif_params, accuracy = pickle.load(open(self.best_test_model_save_path))
            lasagne.layers.set_all_param_values(self.reason_layer.output, reason_params)
            lasagne.layers.set_all_param_values(self.classify_layer.output, classif_params_value)
            print "This model has ", accuracy * 100, "%  accuracy on test set" 

    def begin_train(self):
        N_EPOCHS = 100
        N_BATCH = self.batchsize
        N_TRAIN_INS = len(self.train_ending)
        best_val_accuracy = 0
        best_test_accuracy = 0
        test_threshold = 10000/N_BATCH
        batch_count = 0.0
        start_batch = 0.0

        '''init test'''
        print "initial test..."
        val_result = self.val_set_test()
        print "val set accuracy: ", val_result*100, "%"
        if val_result > best_val_accuracy:
            best_val_accuracy = val_result

        test_accuracy = self.test_set_test()
        print "test set accuracy: ", test_accuracy * 100, "%"
        if test_accuracy > best_test_accuracy:
            best_test_accuracy = test_accuracy
        '''end of init test'''

        for epoch in range(N_EPOCHS):
            print "epoch ", epoch,":"
            shuffled_index_list = utils.shuffle_index(N_TRAIN_INS)

            max_batch = N_TRAIN_INS/N_BATCH

            start_time = time.time()

            total_cost = 0.0
            total_correct_count = 0.0

            for batch in range(max_batch):
                batch_count += 1

                batch_index_list = [shuffled_index_list[i] for i in range(batch * N_BATCH, (batch+1) * N_BATCH)]
                train_story = [[self.train_story[index][i] for index in batch_index_list] for i in range(1, self.story_nsent+1)]
                train_ending = [self.train_ending[index] for index in batch_index_list]

                train_story_matrices = [utils.padding(batch_sent) for batch_sent in train_story]
                train_end_matrix = utils.padding(train_ending)
                # train_end2_matrix = utils.padding(end2)

                train_story_mask = [utils.mask_generator(batch_sent) for batch_sent in train_story]
                train_end_mask = utils.mask_generator(train_ending)
                # train_end2_mask = utils.mask_generator(end2)


                cost, score1, score2 = self.train_func(train_story_matrices[0], train_story_matrices[1], train_story_matrices[2],
                                                               train_story_matrices[3], train_end_matrix,
                                                               train_story_mask[0], train_story_mask[1], train_story_mask[2],
                                                               train_story_mask[3], train_end_mask)



                total_correct_count += np.count_nonzero((score1 - score2).clip(0.0))

                total_cost += cost
                if batch_count % test_threshold == 0:
                    print "accuracy on training set: ", total_correct_count/((batch+1) * N_BATCH)*100.0, "%"

                    print "test on val set..."
                    val_result = self.val_set_test()
                    print "accuracy is: ", val_result*100, "%"
                    if val_result > best_val_accuracy:
                        print "new best! test on test set..."
                        best_val_accuracy = val_result

                        test_accuracy = self.test_set_test()
                        print "test set accuracy: ", test_accuracy*100, "%"
                        if test_accuracy > best_test_accuracy:
                            best_test_accuracy = test_accuracy

            print "======================================="
            print "epoch summary:"
            print "average cost in this epoch: ", total_cost
            print "average speed: ", N_TRAIN_INS/(time.time() - start_time), "instances/s "

            val_result = self.val_set_test()
            print "valid set accuracy: ", val_result*100, "%"
            if val_result > best_val_accuracy:
                print "new best! test on test set..."
                best_val_accuracy = val_result

            test_accuracy = self.test_set_test()
            print "test set accuracy: ", test_accuracy*100, "%"
            if test_accuracy > best_test_accuracy:
                best_test_accuracy = test_accuracy
            print "======================================="


def main(argv):
    wemb_size = None
    if len(argv) > 3:
        wemb_size = argv[3]
    model = Hierachi_RNN(argv[0], argv[1], argv[2], wemb_size)

    print "loading data"
    model.load_data()

    print "model construction"
    model.model_constructor()
    print "construction complete"

    print "training begin!"
    model.begin_train()
    
if __name__ == '__main__':
    main(sys.argv[1:])


