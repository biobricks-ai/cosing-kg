# How to build bricks

1. Create a brick named `{newbrick}` from this template
```
gh repo create biobricks-ai/{newbrick} -p biobricks-ai/brick-template --public
gh repo clone biobricks-ai/{newbrick}
cd newbrick
```

2. Edit stages according to your needs:
    Recommended scripts:
    - ``01_download.sh``
    - ``02_unzip.sh``
    - ``03_build.sh`` calling a function to process individual files like ``csv2parquet.R`` or ``csv2parquet.py``

3. Replace stages in dvc.yaml with your new stages
    
4. Build your brick
```
dvc repro # runs new stages
```

5. Push the data to biobricks.ai
```
dvc push -r s3.biobricks.ai 
```

6. Commit the brick
```
git add -A && git commit -m "some message"
git push
```

7. Monitor the bricktools github action

