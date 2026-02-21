import nltk
nltk.download('punkt')
from nltk.tokenize import sent_tokenize

def split_sentences(text: str):
    return sent_tokenize(text)