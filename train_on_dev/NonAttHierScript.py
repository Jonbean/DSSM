story_rep_type = ['concatenate', 'gothrough']
DNN_settings = ['300x150x75x32x1', '150x75x32x1']
for m in range(2):
    for l in range(5):
        f = open('../adversarial/NonAttHier'+str(l)'.job','w')
        f.write('#!/bin/bash\n')
        f.write('#$ -S /bin/bash\n')
        f.write('#$ -M jontsai@uchicago.edu\n')
        f.write('#$ -N NonAttHier'+str(l)+'\n')
        f.write('#$ -m beasn\n')
        f.write('#$ -o NonAttHier'+str(l)+'.out\n')
        f.write('#$ -e NonAttHier'+str(l)+'.err\n')
        f.write('#$ -r n\n')
        f.write('#$ -cwd\n')
        f.write('SETTING1="300"\n')
        f.write('SETTING2="300"\n')
        f.write('SETTING3="50"\n')
        f.write('SETTING4="'+str(l)+'"\n')
        f.write('SETTING5="0"\n')
        f.write('SETTING6="0.001"\n')
        f.write('SETTING7="1.0"\n')
        f.write('SETTING8="sequence"\n')            
        f.write('SETTING9="default"\n')
        f.write('SETTING10="'+story_rep_type[m]+'"\n')
        f.write('SETTING11="DNN"\n')
        f.write('SETTING12="hinge"\n')
        f.write('SETTING13="'+DNN_settings[m]+'"\n')
        f.write('SETTING14="1"\n')
        f.write('SETTING15="150"\n')
        f.write('SETTING16="0.1"\n')
        f.write('export OMP_NUM_THREADS=1\n')
        f.write('export OPENBLAS_NUM_THREADS=1\n')
        f.write('echo "Start - `date`"\n')
        f.write('/home-nfs/jontsai/anaconda/bin/python BLSTM2BLSTM.py \\\n')
        f.write('$SETTING1 $SETTING2 $SETTING3 $SETTING4 $SETTING5 $SETTING6 $SETTING7 $SETTING8 $SETTING9 \
         $SETTING10 $SETTING11 $SETTING12 $SETTING13 $SETTING14 $SETTING15 $SETTING16\n')
        f.write('echo "End - `date`"\n')
        f.close()