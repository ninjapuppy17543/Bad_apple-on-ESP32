When opening the file, right click on the folder that contains everything and make sure to copy paste this EXACT code onto the terminal:

mkdir frames
.\ffmpeg.exe -i badapple.mp4 -vf "fps=15,scale=128:96,format=gray" frames/frame_%05d.png

That prints out all the frames (there should be 3287 pngs). At a size of 96:128
