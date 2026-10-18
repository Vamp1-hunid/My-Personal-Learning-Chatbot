@echo off
rem Ask the study chatbot a question. Uses Python 3.11 because the default
rem "python" on this machine is 3.15, which has no faiss wheel.
rem Usage:  ask.bat "What is overfitting in machine learning?"
rem         ask.bat --json --show-sources "What is Bayes' theorem?"
"C:\Users\Mulenga Mwamba\AppData\Local\Programs\Python\Python311\python.exe" -m src.cli %*
