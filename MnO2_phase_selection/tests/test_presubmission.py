from MPContribsUsers.mit_mno2.pre_submission import MnO2PhaseFormationEnergies

class MnO2PhaseFormationEnergiesTest:

    def setUp(self):
        self.processor = MnO2PhaseFormationEnergies(formatted_entries='../data/MPContrib_formatted_entries.json',
                                                   hull_entries='../data/MPContrib_hull_entries.json',
                                                   mpid_existing='../data/MPExisting_MnO2_ids.json',
                                                   mpid_new='../data/MPComplete_MnO2_ids.json',
                                                   include_cifs=False)

        with open("../data/MPContrib_mpfile_archieML.txt", "r") as fin: self.archiemlCorrect_noCIF = fin.read()

    def test_archieml(self):
        assert self.processor.get_archieml() == self.archiemlCorrect_noCIF

if __name__ == "__main__":
    test = MnO2PhaseFormationEnergiesTest()
    test.setUp()
    test.test_archieml()
