def test_equal_or_not_equal():
    assert 3 == 3
    assert 3 != 4
def test_boolean():
    validated=True
    assert validated == True
    assert ('hello' == 'world') is False

def test_type():
    assert isinstance(3, int)
    assert isinstance('hello', str)
    assert isinstance([1, 2, 3], list)

def test_greater_than_or_less_than():
    assert 5 > 6
    assert 2 < 4
    assert 10 >= 10
    assert 7 <= 8

def test_list_membership():
    fruits = ['apple', 'banana', 'orange']
    assert 'apple' in fruits
    assert 'grape' not in fruits
    num_list = [1, 2, 3, 4, 5]
    assert 3 in num_list

    
