package dataprovider;

import java.io.IOException;
import java.util.Properties;
import java.util.concurrent.TimeUnit;

import org.json.simple.parser.ParseException;
import org.junit.validator.PublicClassValidator;
import org.openqa.selenium.By;
import org.openqa.selenium.JavascriptExecutor;
import org.openqa.selenium.WebDriver;
import org.openqa.selenium.WebElement;
import org.testng.annotations.BeforeMethod;
import org.testng.annotations.DataProvider;
import org.testng.annotations.Test;

import actions.UIActions;
import levelset_Main.Levelset_HomePage;
import levelset_Test.Test_Class;

public class TestProperty_Trial  { 
	
	 Test_Class setupandNavigating= new Test_Class() ;
	  WebDriver driver ;
	 //  BrowserActions action ;
	   Levelset_HomePage homepage ; 
	   
	  @BeforeMethod
	   public void setup () {
		 driver = setupandNavigating.Setup();  // setup class from Test_Class 
		    
		    new UIActions().click(By.xpath("//a[normalize-space()='Sign in']"));  //click on sign in 
		    new UIActions().click(By.linkText("Signup"));   // click on sign up 
	  } 
	// property file  trial
	  /*
  @Test
  public void f() {   
	  DataProvider property_trial =new DataProvider() ;
	  // ConfigFileReader return data of type properties which i can use to getProperty
	  Properties propertydata =property_trial.ConfigFileReader(); 
	  By Email = By.name("user_email") ;  
	  By Password = By.id("input-pass");
	  
	     driver.findElement(Email).sendKeys(propertydata.getProperty("email")); 
	   driver.findElement(Password).sendKeys(propertydata.getProperty("password"));
	   
	   
	   //    JavascriptExecutor for scrolldown 
	   WebElement Element = driver.findElement((By.xpath("//input[@id='checkbox-agree']")));
	   
	   JavascriptExecutor js = (JavascriptExecutor) driver; 
	   
	   js.executeScript("arguments[0].scrollIntoView();", Element); // first parameter is string with javascrpit code
	                                                                // second is the  object argument.
	   js.executeScript("arguments[0].click();", Element); // to click on checkbox
	 //  new UIActions().click(By.xpath("//input[@id='checkbox-agree']")); // path for checkbox  
	   
	    driver.manage().timeouts().implicitlyWait(10,TimeUnit.SECONDS) ;
	   // for submiting 
	  //   new UIActions().click(By.xpath("//button[normalize-space()='Get Started']")); 
	
	     new UIActions().checkclickable_Button(By.xpath("//button[normalize-space()='Get Started']")); 
	  
  }   */  
	  /*
  @Test 
   public void jsondatatest( ) throws IOException, ParseException { 
	  Dataprovider_Json jsonreader =new Dataprovider_Json() ; 
	  By Email = By.name("user_email") ;  
	  By Password = By.id("input-pass"); 
	     // call function which will get data from file 
	      jsonreader.jsonDataReader(); 
	      System.out.println(jsonreader.email) ;
	     driver.findElement(Email).sendKeys(jsonreader.email); 
	   driver.findElement(Password).sendKeys(jsonreader.password);
	   
  } */ 
	  
	  @DataProvider(name="excel_data")
	  public Object[][] excel_provider() throws IOException{ 
		  ExcelData exceldata =new  ExcelData() ; 
		  // return array with excel data
		 return exceldata.Excelreader() ;
	  }
  // EXCEL 
  @Test (dataProvider = "excel_data")
  public void exceldatatest(String email , String password  )  { 
	       
	  By Email = By.name("user_email") ;  
	  By Password = By.id("input-pass"); 
	    
	      
	     driver.findElement(Email).sendKeys(email); 
	   driver.findElement(Password).sendKeys(password);
	   
 }
}
